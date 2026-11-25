package com.moonhpro4.moonlightvpn

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.util.Locale

/** Urban-VPN style list: search bar on top, every bundled country with its flag. */
class ServerListActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_SELECTED_KEY = "selected_key"
        const val EXTRA_RESULT_KEY = "result_key"
        const val AUTO_KEY = "__auto__"
    }

    private data class Row(
        val key: String,
        val flag: String,
        val title: String,
        val subtitle: String,
        val searchText: String
    )

    private lateinit var allRows: List<Row>
    private lateinit var adapter: RowAdapter
    private lateinit var tvEmpty: TextView
    private var selectedKey: String = AUTO_KEY

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_server_list)
        selectedKey = intent.getStringExtra(EXTRA_SELECTED_KEY) ?: AUTO_KEY

        val autoRow = Row(
            key = AUTO_KEY,
            flag = Flags.GLOBE,
            title = getString(R.string.auto_server),
            subtitle = getString(R.string.auto_server_sub),
            searchText = "auto server random fast best"
        )
        val countryRows = ServerRepository.countries(this).map { c ->
            Row(
                key = c.key,
                flag = c.flag,
                title = c.name,
                subtitle = serverSubtitle(c),
                searchText = ServerRepository.searchText(c)
            )
        }
        allRows = listOf(autoRow) + countryRows

        tvEmpty = findViewById(R.id.tvEmpty)
        adapter = RowAdapter { row -> finishWithResult(row.key) }
        findViewById<RecyclerView>(R.id.rvServers).apply {
            layoutManager = LinearLayoutManager(this@ServerListActivity)
            adapter = this@ServerListActivity.adapter
        }
        adapter.submit(allRows)

        // Real-time filtering while typing.
        findViewById<EditText>(R.id.etSearch).addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val q = s?.toString()?.trim()?.lowercase(Locale.ROOT).orEmpty()
                val filtered = if (q.isEmpty()) allRows else allRows.filter { it.searchText.contains(q) }
                adapter.submit(filtered)
                tvEmpty.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
            }
        })

        findViewById<View>(R.id.btnClose).setOnClickListener { finish() }
    }

    private fun serverSubtitle(c: Country): String =
        getString(if (c.servers.size > 1) R.string.server_multi else R.string.server_single, c.servers.size)

    private fun finishWithResult(key: String) {
        setResult(RESULT_OK, Intent().putExtra(EXTRA_RESULT_KEY, key))
        finish()
    }

    private inner class RowAdapter(private val onClick: (Row) -> Unit) :
        RecyclerView.Adapter<RowAdapter.VH>() {

        private var rows: List<Row> = emptyList()

        fun submit(list: List<Row>) {
            rows = list
            notifyDataSetChanged()
        }

        inner class VH(view: View) : RecyclerView.ViewHolder(view) {
            val flag: TextView = view.findViewById(R.id.tvFlag)
            val name: TextView = view.findViewById(R.id.tvName)
            val sub: TextView = view.findViewById(R.id.tvSub)
            val check: TextView = view.findViewById(R.id.tvCheck)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_server, parent, false)
            return VH(v)
        }

        override fun getItemCount(): Int = rows.size

        override fun onBindViewHolder(holder: VH, position: Int) {
            val row = rows[position]
            holder.flag.text = row.flag
            holder.name.text = row.title
            holder.sub.text = row.subtitle
            holder.check.visibility = if (row.key == selectedKey) View.VISIBLE else View.INVISIBLE
            holder.itemView.setOnClickListener { onClick(row) }
        }
    }
}
