package com.moonhpro4.moonlightvpn

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.CheckBox
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton

class MainActivity : AppCompatActivity(), VpnManager.Listener {

    companion object {
        const val PREFS = "moonlight_prefs"
        const val KEY_SKIP_WARNING = "skip_community_warning"
    }

    /** A connect button + the status line that belongs to it (Normal, Game, Movie tabs). */
    private class Panel(val button: MaterialButton, val status: TextView)

    private lateinit var prefs: SharedPreferences
    private var uiReady = false

    private lateinit var pageHome: View
    private lateinit var pageGame: View
    private lateinit var pageMovie: View
    private lateinit var pageSettings: View

    private lateinit var tvSelFlag: TextView
    private lateinit var tvSelName: TextView
    private lateinit var tvSelSub: TextView
    private lateinit var tvTime: TextView
    private lateinit var tvDown: TextView
    private lateinit var tvUp: TextView
    private val panels = mutableListOf<Panel>()

    /** null = "Auto Server" (default). */
    private var selectedCountry: Country? = null
    private var pendingLaunch: (() -> Unit)? = null

    /** Country chosen in Movie Mode (USA by default). */
    private var selectedMovieKey: String = ServerRepository.STREAMING_COUNTRY
    private val movieRows = mutableMapOf<String, View>()

    private val vpnPermission =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val go = pendingLaunch
            pendingLaunch = null
            if (result.resultCode == RESULT_OK) go?.invoke()
            else Toast.makeText(this, R.string.permission_denied, Toast.LENGTH_SHORT).show()
        }

    private val serverPicker =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                val key = result.data?.getStringExtra(ServerListActivity.EXTRA_RESULT_KEY)
                selectedCountry = if (key == null || key == ServerListActivity.AUTO_KEY) null
                else ServerRepository.countries(this).firstOrNull { it.key == key }
                renderSelection()
            }
        }

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* optional */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE)

        // 1) Internet check on launch.
        if (!NetworkUtils.isOnline(this)) {
            showOfflineDialog()
            return
        }

        VpnManager.init(this)
        setupUi()
        uiReady = true
        askNotificationPermission()
    }

    override fun onStart() {
        super.onStart()
        if (uiReady) {
            VpnManager.addListener(this)
            render()
        }
    }

    override fun onStop() {
        VpnManager.removeListener(this)
        super.onStop()
    }

    override fun onVpnChanged() = render()

    // ------------------------------------------------------------------ dialogs

    private fun showOfflineDialog() {
        AlertDialog.Builder(this)
            .setMessage(R.string.offline_message)
            .setCancelable(false)
            .setPositiveButton(R.string.ok) { _, _ -> finishAffinity() }
            .show()
    }

    private fun showCommunityDialog(onOk: () -> Unit) {
        val view = layoutInflater.inflate(R.layout.dialog_community, null)
        val checkBox = view.findViewById<CheckBox>(R.id.cbDontRemind)
        AlertDialog.Builder(this)
            .setTitle(R.string.community_title)
            .setView(view)
            .setPositiveButton(R.string.ok) { _, _ ->
                if (checkBox.isChecked) {
                    prefs.edit().putBoolean(KEY_SKIP_WARNING, true).apply()
                }
                onOk()
            }
            .show()
    }

    // ------------------------------------------------------------------ UI wiring

    private fun setupUi() {
        pageHome = findViewById(R.id.pageHome)
        pageGame = findViewById(R.id.pageGame)
        pageMovie = findViewById(R.id.pageMovie)
        pageSettings = findViewById(R.id.pageSettings)

        tvSelFlag = findViewById(R.id.tvSelFlag)
        tvSelName = findViewById(R.id.tvSelName)
        tvSelSub = findViewById(R.id.tvSelSub)
        tvTime = findViewById(R.id.tvTime)
        tvDown = findViewById(R.id.tvDown)
        tvUp = findViewById(R.id.tvUp)

        val homePanel = Panel(findViewById(R.id.btnConnectHome), findViewById(R.id.tvStatusHome))
        val gamePanel = Panel(findViewById(R.id.btnConnectGame), findViewById(R.id.tvStatusGame))
        val moviePanel = Panel(findViewById(R.id.btnConnectMovie), findViewById(R.id.tvStatusMovie))
        panels += listOf(homePanel, gamePanel, moviePanel)

        // Normal mode: Auto Server by default, or the country picked in "Show All".
        homePanel.button.setOnClickListener {
            onConnectClicked(
                labelProvider = { selectedCountry?.name ?: getString(R.string.auto_server) },
                poolProvider = { selectedCountry?.servers ?: ServerRepository.servers(this) },
                // Auto Server = random server; a chosen country = fastest server of that country
                fastestProvider = { selectedCountry != null }
            )
        }
        // Game mode: the bundled USA server(s) (fastest one if there are several).
        gamePanel.button.setOnClickListener {
            onConnectClicked(
                labelProvider = { getString(R.string.game_title) },
                poolProvider = { ServerRepository.byCountry(this, ServerRepository.GAME_COUNTRY) }
            )
        }
        // Movie mode: the country picked in the Movie tab.
        moviePanel.button.setOnClickListener {
            onConnectClicked(
                labelProvider = { getString(R.string.movie_title) },
                poolProvider = { ServerRepository.byCountry(this, selectedMovieKey) }
            )
        }
        buildMovieList()

        findViewById<View>(R.id.btnShowAll).setOnClickListener {
            val intent = Intent(this, ServerListActivity::class.java)
                .putExtra(ServerListActivity.EXTRA_SELECTED_KEY,
                    selectedCountry?.key ?: ServerListActivity.AUTO_KEY)
            serverPicker.launch(intent)
        }

        findViewById<View>(R.id.btnJoin).setOnClickListener {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(getString(R.string.join_url))))
            } catch (e: ActivityNotFoundException) {
                Toast.makeText(this, getString(R.string.join_url), Toast.LENGTH_LONG).show()
            }
        }

        findViewById<BottomNavigationView>(R.id.bottomNav).setOnItemSelectedListener { item ->
            pageHome.visibility = if (item.itemId == R.id.nav_home) View.VISIBLE else View.GONE
            pageGame.visibility = if (item.itemId == R.id.nav_game) View.VISIBLE else View.GONE
            pageMovie.visibility = if (item.itemId == R.id.nav_movie) View.VISIBLE else View.GONE
            pageSettings.visibility = if (item.itemId == R.id.nav_settings) View.VISIBLE else View.GONE
            true
        }

        renderSelection()
    }

    // ------------------------------------------------------------------ movie mode

    private fun buildMovieList() {
        val list = findViewById<android.widget.LinearLayout>(R.id.movieList)
        list.removeAllViews()
        movieRows.clear()
        val options = ServerRepository.movieCountries(this)
        if (options.none { it.key == selectedMovieKey } && options.isNotEmpty()) {
            selectedMovieKey = options.first().key
        }
        for (c in options) {
            val row = layoutInflater.inflate(R.layout.item_movie, list, false)
            row.findViewById<TextView>(R.id.tvMovieFlag).text = c.flag
            row.findViewById<TextView>(R.id.tvMovieName).text = c.name
            row.findViewById<TextView>(R.id.tvMovieTag).setText(
                if (c.key == ServerRepository.STREAMING_COUNTRY) R.string.movie_tag_streaming
                else R.string.movie_tag_other
            )
            row.setOnClickListener {
                selectedMovieKey = c.key
                renderMovieSelection()
            }
            movieRows[c.key] = row
            list.addView(row)
        }
        renderMovieSelection()
    }

    private fun renderMovieSelection() {
        for ((key, row) in movieRows) {
            val selected = key == selectedMovieKey
            row.setBackgroundResource(if (selected) R.drawable.bg_card_selected else R.drawable.bg_card)
            row.findViewById<TextView>(R.id.tvMovieCheck).visibility =
                if (selected) View.VISIBLE else View.INVISIBLE
        }
    }

    // ------------------------------------------------------------------ connecting

    private fun onConnectClicked(
        labelProvider: () -> String,
        poolProvider: () -> List<VpnServer>,
        fastestProvider: () -> Boolean = { true }
    ) {
        val state = VpnManager.state
        if (state == VpnState.CONNECTING || state == VpnState.CONNECTED) {
            VpnManager.disconnect()
            return
        }
        if (!NetworkUtils.isOnline(this)) {
            Toast.makeText(this, R.string.no_internet_toast, Toast.LENGTH_SHORT).show()
            return
        }
        val start = { VpnManager.connect(this, labelProvider(), poolProvider(), fastestProvider()) }

        // 2) Community-server warning every time, unless the user ticked "Don't remind me again".
        if (prefs.getBoolean(KEY_SKIP_WARNING, false)) {
            ensureVpnPermissionThen(start)
        } else {
            showCommunityDialog { ensureVpnPermissionThen(start) }
        }
    }

    /** Shows Android's native "Connection request" VPN dialog when needed. */
    private fun ensureVpnPermissionThen(go: () -> Unit) {
        val intent = VpnService.prepare(this)
        if (intent == null) {
            go()
        } else {
            pendingLaunch = go
            vpnPermission.launch(intent)
        }
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    // ------------------------------------------------------------------ rendering

    private fun renderSelection() {
        val c = selectedCountry
        if (c == null) {
            tvSelFlag.text = Flags.GLOBE
            tvSelName.text = getString(R.string.auto_server)
            tvSelSub.text = getString(R.string.auto_server_sub)
        } else {
            tvSelFlag.text = c.flag
            tvSelName.text = c.name
            tvSelSub.text = getString(if (c.servers.size > 1) R.string.server_multi else R.string.server_single, c.servers.size)
        }
    }

    private fun render() {
        if (!uiReady) return
        val state = VpnManager.state
        val server = VpnManager.current
        val where = if (server != null) "${Flags.fromCode(server.countryCode)} ${server.countryName}"
        else VpnManager.label

        val buttonText: Int
        val color: Int
        val statusText: String
        when (state) {
            VpnState.CONNECTED -> {
                buttonText = R.string.btn_disconnect
                color = R.color.connected
                statusText = getString(R.string.status_connected, where)
            }
            VpnState.CONNECTING -> {
                buttonText = R.string.btn_connecting
                color = R.color.connecting
                statusText = getString(R.string.status_connecting, where)
            }
            VpnState.FAILED -> {
                buttonText = R.string.btn_connect
                color = R.color.primary
                statusText = getString(R.string.status_failed)
            }
            VpnState.DISCONNECTED -> {
                buttonText = R.string.btn_connect
                color = R.color.primary
                statusText = getString(R.string.status_off)
            }
        }
        for (p in panels) {
            p.button.setText(buttonText)
            p.button.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, color))
            p.status.text = statusText
        }

        val connected = state == VpnState.CONNECTED
        tvTime.text = "⏱ " + (if (connected) VpnManager.duration else "00:00:00")
        tvDown.text = "↓ " + (if (connected && VpnManager.bytesIn.isNotBlank()) VpnManager.bytesIn else "–")
        tvUp.text = "↑ " + (if (connected && VpnManager.bytesOut.isNotBlank()) VpnManager.bytesOut else "–")
    }
}
