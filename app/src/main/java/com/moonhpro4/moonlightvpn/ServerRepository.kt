package com.moonhpro4.moonlightvpn

import android.content.Context
import java.util.Locale

/** One bundled .ovpn profile (app/src/main/assets/vpns/...). Nothing here touches the network. */
data class VpnServer(
    val fileName: String,
    val countryKey: String,
    val countryName: String,
    val countryCode: String,
    val host: String,
    val protocol: String,
    val port: Int
) {
    val assetPath: String get() = "vpns/$fileName"
}

/** A country with every bundled server for it (USA and Russia have two). */
data class Country(
    val key: String,
    val name: String,
    val code: String,
    val servers: List<VpnServer>
) {
    val flag: String get() = Flags.fromCode(code)
}

object Flags {
    const val GLOBE = "\uD83C\uDF10"

    /** "JP" -> 🇯🇵 (regional indicator symbols, rendered by the phone's own emoji font, fully offline). */
    fun fromCode(code: String): String {
        if (code.length != 2) return GLOBE
        val sb = StringBuilder()
        for (ch in code.uppercase(Locale.ROOT)) {
            if (ch < 'A' || ch > 'Z') return GLOBE
            sb.appendCodePoint(0x1F1E6 + (ch - 'A'))
        }
        return sb.toString()
    }
}

object ServerRepository {

    // Fixed profiles used by the Game / Movie tabs.
    val GAME_FILES = listOf(
        "usa-141.239.115.116-tcp1560.ovpn",
        "usa-159.118.158.2-tcp1555.ovpn"
    )
    val MOVIE_FILES = listOf("spain-87.222.100.131-udp1661.ovpn")

    /** file-name prefix -> (display name, ISO 3166 code) */
    private val META: Map<String, Pair<String, String>> = mapOf(
        "argentina" to ("Argentina" to "AR"),
        "australia" to ("Australia" to "AU"),
        "bangladesh" to ("Bangladesh" to "BD"),
        "belarus" to ("Belarus" to "BY"),
        "brazil" to ("Brazil" to "BR"),
        "bulgaria" to ("Bulgaria" to "BG"),
        "costa-rica" to ("Costa Rica" to "CR"),
        "croatia-hrvatska" to ("Croatia" to "HR"),
        "czech-republic" to ("Czech Republic" to "CZ"),
        "ecuador" to ("Ecuador" to "EC"),
        "finland" to ("Finland" to "FI"),
        "france" to ("France" to "FR"),
        "georgia" to ("Georgia" to "GE"),
        "grenada" to ("Grenada" to "GD"),
        "hong-kong" to ("Hong Kong" to "HK"),
        "hungary" to ("Hungary" to "HU"),
        "india" to ("India" to "IN"),
        "indonesia" to ("Indonesia" to "ID"),
        "iran-islamic-republic-of" to ("Iran" to "IR"),
        "italy" to ("Italy" to "IT"),
        "japan" to ("Japan" to "JP"),
        "lithuania" to ("Lithuania" to "LT"),
        "mexico" to ("Mexico" to "MX"),
        "moldova" to ("Moldova" to "MD"),
        "myanmar" to ("Myanmar" to "MM"),
        "netherlands" to ("Netherlands" to "NL"),
        "new-zealand" to ("New Zealand" to "NZ"),
        "peru" to ("Peru" to "PE"),
        "portugal" to ("Portugal" to "PT"),
        "romania" to ("Romania" to "RO"),
        "russia" to ("Russia" to "RU"),
        "south-africa" to ("South Africa" to "ZA"),
        "south-korea" to ("South Korea" to "KR"),
        "spain" to ("Spain" to "ES"),
        "sweden" to ("Sweden" to "SE"),
        "thailand" to ("Thailand" to "TH"),
        "uk" to ("United Kingdom" to "GB"),
        "ukraine" to ("Ukraine" to "UA"),
        "usa" to ("United States" to "US"),
        "vietnam" to ("Vietnam" to "VN"),
        "yemen" to ("Yemen" to "YE")
    )

    /** Extra words the search box also understands. */
    private val ALIASES: Map<String, String> = mapOf(
        "usa" to "usa us america united states",
        "uk" to "uk gb britain england united kingdom",
        "south-korea" to "korea",
        "czech-republic" to "czechia",
        "iran-islamic-republic-of" to "iran persia",
        "croatia-hrvatska" to "croatia hrvatska"
    )

    // e.g. "croatia-hrvatska--150.40.105.15-tcp443.ovpn" -> key "croatia-hrvatska"
    private val FILE_RE =
        Regex("^(.+?)-+(\\d{1,3}(?:\\.\\d{1,3}){3})-(tcp|udp)(\\d+)\\.ovpn$", RegexOption.IGNORE_CASE)

    @Volatile private var cachedServers: List<VpnServer>? = null
    @Volatile private var cachedCountries: List<Country>? = null

    fun servers(context: Context): List<VpnServer> {
        cachedServers?.let { return it }
        val files = context.applicationContext.assets.list("vpns")?.toList() ?: emptyList()
        val list = files.mapNotNull { parse(it) }
        cachedServers = list
        return list
    }

    fun countries(context: Context): List<Country> {
        cachedCountries?.let { return it }
        val result = servers(context)
            .groupBy { it.countryKey }
            .map { (key, list) ->
                Country(key, list.first().countryName, list.first().countryCode, list)
            }
            .sortedBy { it.name }
        cachedCountries = result
        return result
    }

    fun byFiles(context: Context, names: List<String>): List<VpnServer> {
        val all = servers(context)
        return names.mapNotNull { n -> all.firstOrNull { it.fileName == n } }
    }

    /** Text used by the search box for one country. */
    fun searchText(country: Country): String =
        (country.name + " " + country.key.replace('-', ' ') + " " + country.code + " " +
            (ALIASES[country.key] ?: "")).lowercase(Locale.ROOT)

    /** Reads the .ovpn text from the APK's own assets. */
    fun readConfig(context: Context, server: VpnServer): String =
        context.applicationContext.assets.open(server.assetPath).bufferedReader().use { it.readText() }

    private fun parse(fileName: String): VpnServer? {
        val m = FILE_RE.matchEntire(fileName) ?: return null
        val key = m.groupValues[1].trim('-').lowercase(Locale.ROOT)
        val meta = META[key]
        val name = meta?.first ?: key.split('-').joinToString(" ") {
            it.replaceFirstChar { c -> c.uppercase() }
        }
        return VpnServer(
            fileName = fileName,
            countryKey = key,
            countryName = name,
            countryCode = meta?.second ?: "",
            host = m.groupValues[2],
            protocol = m.groupValues[3].lowercase(Locale.ROOT),
            port = m.groupValues[4].toInt()
        )
    }
}
