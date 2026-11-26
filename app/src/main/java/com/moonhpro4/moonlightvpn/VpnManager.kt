package com.moonhpro4.moonlightvpn

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Handler
import android.os.Looper
import android.os.RemoteException
import android.os.SystemClock
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import de.blinkt.openvpn.OpenVpnApi
import de.blinkt.openvpn.core.OpenVPNService
import de.blinkt.openvpn.core.OpenVPNThread
import de.blinkt.openvpn.core.VpnStatus
import java.util.concurrent.CopyOnWriteArrayList

enum class VpnState { DISCONNECTED, CONNECTING, CONNECTED, FAILED }

/**
 * Thin wrapper around the native OpenVPN engine (ics-openvpn "vpnLib").
 * Takes a pool of bundled servers, connects to the fastest one and automatically tries the next
 * one (max 3) if a server does not answer. Runs entirely on-device.
 */
object VpnManager {

    interface Listener { fun onVpnChanged() }

    private const val MAX_ATTEMPTS = 3
    private const val CONNECT_TIMEOUT_MS = 35_000L
    private const val RETRY_DELAY_MS = 1_500L
    private const val IGNORE_STALE_MS = 2_500L

    var state: VpnState = VpnState.DISCONNECTED
        private set
    var label: String = ""
        private set
    var current: VpnServer? = null
        private set
    var duration: String = "00:00:00"
        private set
    var bytesIn: String = ""
        private set
    var bytesOut: String = ""
        private set

    private val listeners = CopyOnWriteArrayList<Listener>()
    private val handler = Handler(Looper.getMainLooper())
    private var appContext: Context? = null
    private var queue = ArrayDeque<VpnServer>()
    private var userStopped = false
    private var failingOver = false
    private var lastStartAt = 0L
    private var generation = 0

    private val timeoutRunnable = Runnable {
        if (state == VpnState.CONNECTING) failCurrent()
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            intent ?: return
            intent.getStringExtra("state")?.let { onRawState(it.uppercase()) }
            val d = intent.getStringExtra("duration")
            if (d != null) {
                duration = d
                bytesIn = intent.getStringExtra("byteIn") ?: ""
                bytesOut = intent.getStringExtra("byteOut") ?: ""
                notifyListeners()
            }
        }
    }

    fun addListener(l: Listener) { if (!listeners.contains(l)) listeners.add(l) }
    fun removeListener(l: Listener) { listeners.remove(l) }
    private fun notifyListeners() { listeners.forEach { it.onVpnChanged() } }

    fun init(context: Context) {
        if (appContext != null) return
        val app = context.applicationContext
        appContext = app
        VpnStatus.initLogCache(app.cacheDir)
        LocalBroadcastManager.getInstance(app)
            .registerReceiver(receiver, IntentFilter("connectionState"))
        // App re-opened while a tunnel is already up.
        if (OpenVPNService.getStatus()?.uppercase() == "CONNECTED") {
            state = VpnState.CONNECTED
        }
    }

    /**
     * Connects to a server of [pool]. With [fastest] = true (country picks, Game, Movie) the servers
     * are timed on-device first and tried fastest-first (max 3). With [fastest] = false (Auto Server)
     * a random order is used instead.
     */
    fun connect(context: Context, label: String, pool: List<VpnServer>, fastest: Boolean = true) {
        init(context)
        if (pool.isEmpty()) return
        handler.removeCallbacksAndMessages(null)
        userStopped = false
        this.label = label
        val gen = ++generation
        val wasRunning = state == VpnState.CONNECTING || state == VpnState.CONNECTED
        // While timing servers (or stopping an old tunnel) ignore engine broadcasts.
        failingOver = true
        current = null
        if (wasRunning) OpenVPNThread.stop()
        setState(VpnState.CONNECTING)

        fun begin(ordered: List<VpnServer>) {
            if (gen != generation || userStopped) return
            queue = ArrayDeque(ordered.take(MAX_ATTEMPTS))
            handler.postDelayed({
                if (gen == generation && !userStopped) startNext()
            }, if (wasRunning) RETRY_DELAY_MS else 0L)
        }
        if (pool.size == 1) {
            begin(pool)
        } else if (!fastest) {
            begin(pool.shuffled())
        } else {
            Thread {
                val ordered = LatencyProbe.fastestFirst(pool)
                handler.post { begin(ordered) }
            }.start()
        }
    }

    fun disconnect() {
        generation++ // cancels any server timing still in progress
        userStopped = true
        failingOver = false
        queue.clear()
        handler.removeCallbacksAndMessages(null)
        OpenVPNThread.stop()
        setState(VpnState.DISCONNECTED)
    }

    private fun startNext() {
        val ctx = appContext ?: return
        val server = queue.removeFirstOrNull()
        if (server == null) {
            failingOver = false
            setState(VpnState.FAILED)
            return
        }
        current = server
        failingOver = false
        duration = "00:00:00"; bytesIn = ""; bytesOut = ""
        lastStartAt = SystemClock.elapsedRealtime()
        setState(VpnState.CONNECTING)
        try {
            val config = prepareConfig(ServerRepository.readConfig(ctx, server))
            // VPN Gate style community servers use the public credentials vpn / vpn.
            OpenVpnApi.startVpn(ctx, config, label, "vpn", "vpn", null)
            handler.removeCallbacks(timeoutRunnable)
            handler.postDelayed(timeoutRunnable, CONNECT_TIMEOUT_MS)
        } catch (e: RemoteException) {
            failCurrent()
        } catch (e: Exception) {
            failCurrent()
        }
    }

    private fun failCurrent() {
        handler.removeCallbacks(timeoutRunnable)
        if (userStopped) return
        failingOver = true
        OpenVPNThread.stop()
        if (queue.isEmpty()) {
            failingOver = false
            setState(VpnState.FAILED)
        } else {
            handler.postDelayed({ startNext() }, RETRY_DELAY_MS)
        }
    }

    private fun onRawState(raw: String) {
        when (raw) {
            "CONNECTED" -> {
                handler.removeCallbacks(timeoutRunnable)
                failingOver = false
                setState(VpnState.CONNECTED)
            }
            "DISCONNECTED", "NOPROCESS", "NOTCONNECTED", "EXITING", "DENIED" -> {
                if (failingOver) return
                val stale = SystemClock.elapsedRealtime() - lastStartAt < IGNORE_STALE_MS
                if (state == VpnState.CONNECTING) {
                    if (stale || userStopped) return
                    if (raw == "DENIED") setState(VpnState.DISCONNECTED) else failCurrent()
                } else {
                    handler.removeCallbacks(timeoutRunnable)
                    setState(VpnState.DISCONNECTED)
                }
            }
            "AUTH_FAILED", "ERROR" -> {
                if (failingOver || userStopped) return
                if (state == VpnState.CONNECTING) failCurrent() else setState(VpnState.FAILED)
            }
            else -> { // WAIT, AUTH, RESOLVE, TCP_CONNECT, GET_CONFIG, ASSIGN_IP, ADD_ROUTES, RECONNECTING, NONETWORK ...
                if (!failingOver && !userStopped) setState(VpnState.CONNECTING)
            }
        }
    }

    private fun setState(newState: VpnState) {
        state = newState
        notifyListeners()
    }

    /**
     * OpenVPN 2.6+ needs an explicit fallback for the legacy "cipher" option used by
     * community servers, otherwise it can refuse to negotiate.
     */
    private fun prepareConfig(raw: String): String {
        var cfg = raw.replace("\r\n", "\n")
        val cipher = Regex("(?m)^cipher\\s+(\\S+)").find(cfg)?.groupValues?.get(1)
        if (cipher != null && !cfg.contains("data-ciphers-fallback")) {
            cfg = cfg.replaceFirst(Regex("(?m)^cipher\\s+\\S+"), "cipher $cipher\ndata-ciphers-fallback $cipher")
        }
        return cfg
    }
}
