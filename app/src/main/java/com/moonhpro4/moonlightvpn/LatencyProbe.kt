package com.moonhpro4.moonlightvpn

import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Measures, on the phone itself, how fast each candidate server answers (TCP connect time to the
 * host/port written in its .ovpn file) and orders them fastest first. No API, no cloud.
 * Must be called from a background thread.
 */
object LatencyProbe {
    private const val UNREACHABLE = Long.MAX_VALUE
    private const val UNMEASURABLE = Long.MAX_VALUE - 1 // UDP servers cannot be probed this way

    fun fastestFirst(pool: List<VpnServer>, timeoutMs: Int = 3000): List<VpnServer> {
        if (pool.size < 2) return pool
        val times = LongArray(pool.size) { UNREACHABLE }
        val latch = CountDownLatch(pool.size)
        pool.forEachIndexed { i, server ->
            Thread {
                try {
                    times[i] = measure(server, timeoutMs)
                } finally {
                    latch.countDown()
                }
            }.start()
        }
        latch.await(timeoutMs * 2L + 1000L, TimeUnit.MILLISECONDS)
        return pool.indices.sortedBy { times[it] }.map { pool[it] }
    }

    private fun measure(server: VpnServer, timeoutMs: Int): Long {
        if (server.protocol != "tcp") return UNMEASURABLE
        var best = UNREACHABLE
        repeat(2) { // two tries, keep the better one
            val start = System.nanoTime()
            try {
                Socket().use { it.connect(InetSocketAddress(server.host, server.port), timeoutMs) }
                best = minOf(best, System.nanoTime() - start)
            } catch (e: IOException) {
                // unreachable on this try
            }
        }
        return best
    }
}
