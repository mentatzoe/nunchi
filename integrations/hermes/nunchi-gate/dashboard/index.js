/**
 * Nunchi Gate Dashboard Tab
 *
 * Plain-JS IIFE — no build step required.  Runs in the Hermes dashboard host
 * page, which exposes React and UI components on window.__HERMES_PLUGIN_SDK__
 * and registers plugins via window.__HERMES_PLUGINS__.register().
 *
 * Features:
 *   - Per-channel effective config table with provenance badges and inline
 *     editable senders / verbosity / enabled fields.
 *   - Global override section.
 *   - Save button (PUT /api/plugins/nunchi/state).
 *   - Reset-overrides button (PUT with empty global+channels).
 *   - Receipts panel (GET /api/plugins/nunchi/receipts) polling every 5 s.
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  var PLUGINS = window.__HERMES_PLUGINS__;
  if (!SDK || !PLUGINS) {
    console.warn("[nunchi] SDK not ready — retrying in 500 ms");
    setTimeout(function () {
      var s = document.createElement("script");
      s.src = document.currentScript
        ? document.currentScript.src
        : "/dashboard-plugins/nunchi/index.js";
      document.head.appendChild(s);
    }, 500);
    return;
  }

  var React = SDK.React;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useCallback = SDK.hooks.useCallback;
  var fetchJSON = SDK.fetchJSON;
  var h = React.createElement;

  // -------------------------------------------------------------------------
  // Constants
  // -------------------------------------------------------------------------
  var API_BASE = "/api/plugins/nunchi";
  var POLL_INTERVAL_MS = 5000;
  var SENDERS_OPTIONS = ["all", "humans", "allowlist"];
  var VERBOSITY_OPTIONS = ["minimal", "normal", "debug"];

  // -------------------------------------------------------------------------
  // Utility: provenance badge style
  // -------------------------------------------------------------------------
  function Badge(text, color) {
    return h(
      "span",
      {
        style: {
          marginLeft: "6px",
          padding: "1px 6px",
          borderRadius: "4px",
          fontSize: "10px",
          fontWeight: "600",
          background: color || "#334155",
          color: "#e2e8f0",
          letterSpacing: "0.03em",
        },
      },
      text
    );
  }

  function provenanceBadge(key, chOverrides, globalOverrides) {
    if (chOverrides && key in chOverrides)
      return Badge("channel-override", "#7c3aed");
    if (globalOverrides && key in globalOverrides)
      return Badge("global-override", "#0369a1");
    return null;
  }

  // -------------------------------------------------------------------------
  // SelectField: labelled dropdown
  // -------------------------------------------------------------------------
  function SelectField(props) {
    return h(
      "label",
      { style: { display: "flex", alignItems: "center", gap: "6px" } },
      h("span", { style: { fontSize: "12px", color: "#94a3b8", minWidth: "72px" } }, props.label),
      h(
        "select",
        {
          value: props.value || "",
          onChange: function (e) { props.onChange(e.target.value); },
          style: {
            background: "#1e293b",
            color: "#e2e8f0",
            border: "1px solid #334155",
            borderRadius: "4px",
            padding: "2px 6px",
            fontSize: "12px",
          },
        },
        props.options.map(function (o) {
          return h("option", { key: o, value: o }, o);
        })
      ),
      props.badge || null
    );
  }

  // -------------------------------------------------------------------------
  // ChannelRow: editable row for one channel
  // -------------------------------------------------------------------------
  function ChannelRow(props) {
    var cid = props.cid;
    var eff = props.effective || {};
    var chOv = props.chOverrides || {};
    var globalOv = props.globalOverrides || {};

    var isIntroduced = props.isIntroduced;

    return h(
      "div",
      {
        style: {
          padding: "10px 12px",
          borderRadius: "6px",
          background: "#0f172a",
          border: "1px solid #1e293b",
          marginBottom: "8px",
        },
      },
      h(
        "div",
        {
          style: {
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginBottom: "8px",
          },
        },
        h(
          "code",
          { style: { fontSize: "12px", color: "#38bdf8" } },
          cid
        ),
        isIntroduced ? Badge("state-introduced", "#065f46") : null,
        props.effective === null
          ? Badge("not gated", "#991b1b")
          : null
      ),
      props.effective === null
        ? h("p", { style: { fontSize: "11px", color: "#64748b", margin: 0 } },
            "Disabled by state or not matched by config.yaml")
        : h(
            "div",
            { style: { display: "flex", flexDirection: "column", gap: "6px" } },
            h(SelectField, {
              label: "enabled",
              value: String(eff.enabled !== false),
              options: ["true", "false"],
              onChange: function (v) { props.onChange(cid, "enabled", v === "true"); },
              badge: provenanceBadge("enabled", chOv, globalOv),
            }),
            h(SelectField, {
              label: "senders",
              value: eff.senders || "all",
              options: SENDERS_OPTIONS,
              onChange: function (v) { props.onChange(cid, "senders", v); },
              badge: provenanceBadge("senders", chOv, globalOv),
            }),
            h(SelectField, {
              label: "verbosity",
              value: eff.verbosity || "normal",
              options: VERBOSITY_OPTIONS,
              onChange: function (v) { props.onChange(cid, "verbosity", v); },
              badge: provenanceBadge("verbosity", chOv, globalOv),
            })
          )
    );
  }

  // -------------------------------------------------------------------------
  // ReceiptsPanel: polls GET /receipts every 5 s
  // -------------------------------------------------------------------------
  function ReceiptsPanel() {
    var _s = useState([]);
    var receipts = _s[0];
    var setReceipts = _s[1];

    var _e = useState(null);
    var err = _e[0];
    var setErr = _e[1];

    var poll = useCallback(function () {
      fetchJSON(API_BASE + "/receipts?limit=50")
        .then(function (data) {
          setReceipts(data.receipts || []);
          setErr(null);
        })
        .catch(function (e) { setErr(String(e)); });
    }, []);

    useEffect(function () {
      poll();
      var id = setInterval(poll, POLL_INTERVAL_MS);
      return function () { clearInterval(id); };
    }, [poll]);

    return h(
      "div",
      { style: { marginTop: "24px" } },
      h(
        "h3",
        { style: { fontSize: "13px", fontWeight: "600", color: "#94a3b8", marginBottom: "8px" } },
        "Gate Receipts (newest first, polling every 5 s)"
      ),
      err
        ? h("p", { style: { color: "#f87171", fontSize: "12px" } }, err)
        : receipts.length === 0
        ? h("p", { style: { color: "#64748b", fontSize: "12px" } }, "No receipts yet.")
        : h(
            "div",
            {
              style: {
                maxHeight: "320px",
                overflowY: "auto",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
              },
            },
            receipts.map(function (r, i) {
              var verdict = r.verdict || r.action || "?";
              var color =
                verdict === "PASS" || r.action === "skip"
                  ? "#7f1d1d"
                  : verdict === "SPEAK" || r.action === "allow"
                  ? "#14532d"
                  : "#1e3a5f";
              return h(
                "div",
                {
                  key: i,
                  style: {
                    background: color,
                    padding: "5px 8px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    color: "#e2e8f0",
                    display: "flex",
                    gap: "8px",
                    alignItems: "flex-start",
                  },
                },
                h("span", { style: { opacity: 0.7, minWidth: "80px" } },
                  r.ts ? new Date(r.ts * 1000).toLocaleTimeString() : ""),
                h("span", { style: { fontWeight: "700", minWidth: "48px" } }, verdict),
                h("span", { style: { opacity: 0.8 } },
                  r.trigger_author ? ("@" + r.trigger_author + " ") : ""),
                r.reasons && r.reasons[0]
                  ? h("span", { style: { opacity: 0.7, fontSize: "10px" } }, r.reasons[0])
                  : null,
                h("span", { style: { opacity: 0.5, marginLeft: "auto" } },
                  (r.channel_ids || []).join(", "))
              );
            })
          )
    );
  }

  // -------------------------------------------------------------------------
  // Main plugin component
  // -------------------------------------------------------------------------
  function NunchiPanel() {
    var _state = useState({ baseline: {}, overrides: {}, effective: {} });
    var stateData = _state[0];
    var setStateData = _state[1];

    var _pending = useState({});
    var pending = _pending[0];
    var setPending = _pending[1];

    var _status = useState(null);
    var status = _status[0];
    var setStatus = _status[1];

    var _loading = useState(true);
    var loading = _loading[0];
    var setLoading = _loading[1];

    var load = useCallback(function () {
      setLoading(true);
      fetchJSON(API_BASE + "/state")
        .then(function (data) {
          setStateData(data);
          setLoading(false);
        })
        .catch(function (e) {
          setStatus("Error loading state: " + e);
          setLoading(false);
        });
    }, []);

    useEffect(function () { load(); }, [load]);

    var handleChannelChange = useCallback(
      function (cid, key, value) {
        setPending(function (prev) {
          var channels = Object.assign({}, prev.channels || {});
          var ch = Object.assign({}, channels[cid] || {});
          ch[key] = value;
          channels[cid] = ch;
          return Object.assign({}, prev, { channels: channels });
        });
      },
      []
    );

    var handleGlobalChange = useCallback(
      function (key, value) {
        setPending(function (prev) {
          var g = Object.assign({}, prev.global || {});
          g[key] = value;
          return Object.assign({}, prev, { global: g });
        });
      },
      []
    );

    var save = useCallback(
      function () {
        fetchJSON(API_BASE + "/state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pending),
        })
          .then(function () {
            setStatus("Saved.");
            setPending({});
            load();
          })
          .catch(function (e) { setStatus("Save failed: " + e); });
      },
      [pending, load]
    );

    var resetAll = useCallback(
      function () {
        if (!window.confirm("Clear all nunchi-gate runtime overrides?")) return;
        fetchJSON(API_BASE + "/state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ global: {}, channels: {} }),
        })
          .then(function () {
            setStatus("All overrides cleared.");
            setPending({});
            load();
          })
          .catch(function (e) { setStatus("Reset failed: " + e); });
      },
      [load]
    );

    var effective = stateData.effective || {};
    var overrides = stateData.overrides || {};
    var globalOv = overrides.global || {};
    var chStates = overrides.channels || {};

    // Merge pending changes into display
    var pendingGlobal = pending.global || {};
    var pendingChannels = pending.channels || {};
    var allCids = Array.from(
      new Set(Object.keys(effective).concat(Object.keys(pendingChannels)))
    ).sort();

    // Determine state-introduced channels (those absent from baseline channels)
    var baselineChannels = {};
    var baselineChs = stateData.baseline && stateData.baseline.channels;
    if (baselineChs && typeof baselineChs === "object" && !Array.isArray(baselineChs)) {
      Object.keys(baselineChs).forEach(function (k) {
        if (k !== "*") baselineChannels[k] = true;
      });
    } else if (Array.isArray(baselineChs)) {
      baselineChs.forEach(function (k) { baselineChannels[k] = true; });
    }

    return h(
      "div",
      {
        style: {
          padding: "20px",
          maxWidth: "780px",
          color: "#e2e8f0",
          fontFamily: "'Inter', system-ui, sans-serif",
        },
      },
      h(
        "div",
        { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" } },
        h("h2", { style: { fontSize: "18px", fontWeight: "700", margin: 0 } }, "Nunchi Gate"),
        loading ? h("span", { style: { fontSize: "12px", color: "#94a3b8" } }, "Loading…") : null,
        status
          ? h("span", { style: { fontSize: "12px", color: "#38bdf8" } }, status)
          : null
      ),

      // Global overrides section
      h(
        "div",
        {
          style: {
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: "8px",
            padding: "12px 16px",
            marginBottom: "16px",
          },
        },
        h(
          "h3",
          { style: { fontSize: "13px", fontWeight: "600", color: "#94a3b8", marginBottom: "8px" } },
          "Global Overrides"
        ),
        h(SelectField, {
          label: "senders",
          value:
            pendingGlobal.senders || globalOv.senders || "",
          options: ["", "all", "humans", "allowlist"],
          onChange: function (v) {
            handleGlobalChange("senders", v || undefined);
          },
          badge: globalOv.senders ? Badge("override", "#0369a1") : null,
        }),
        h(SelectField, {
          label: "verbosity",
          value: pendingGlobal.verbosity || globalOv.verbosity || "",
          options: ["", "minimal", "normal", "debug"],
          onChange: function (v) {
            handleGlobalChange("verbosity", v || undefined);
          },
          badge: globalOv.verbosity ? Badge("override", "#0369a1") : null,
        })
      ),

      // Per-channel rows
      h(
        "div",
        { style: { marginBottom: "16px" } },
        h(
          "h3",
          {
            style: {
              fontSize: "13px",
              fontWeight: "600",
              color: "#94a3b8",
              marginBottom: "8px",
            },
          },
          "Channels"
        ),
        allCids.length === 0
          ? h(
              "p",
              { style: { fontSize: "12px", color: "#64748b" } },
              "No channels configured."
            )
          : allCids.map(function (cid) {
              var eff = effective[cid] !== undefined
                ? effective[cid]
                : null;
              // Merge pending channel overrides into effective display
              var displayEff = eff;
              if (eff && pendingChannels[cid]) {
                displayEff = Object.assign({}, eff, pendingChannels[cid]);
              }
              return h(ChannelRow, {
                key: cid,
                cid: cid,
                effective: displayEff,
                chOverrides: chStates[cid] || {},
                globalOverrides: globalOv,
                isIntroduced: !baselineChannels[cid],
                onChange: handleChannelChange,
              });
            })
      ),

      // Action buttons
      h(
        "div",
        { style: { display: "flex", gap: "8px", marginBottom: "16px" } },
        h(
          "button",
          {
            onClick: save,
            style: {
              padding: "6px 16px",
              borderRadius: "6px",
              background: "#2563eb",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              fontSize: "13px",
              fontWeight: "600",
            },
          },
          "Save"
        ),
        h(
          "button",
          {
            onClick: resetAll,
            style: {
              padding: "6px 16px",
              borderRadius: "6px",
              background: "#7f1d1d",
              color: "#fca5a5",
              border: "none",
              cursor: "pointer",
              fontSize: "13px",
            },
          },
          "Reset All Overrides"
        ),
        h(
          "button",
          {
            onClick: load,
            style: {
              padding: "6px 16px",
              borderRadius: "6px",
              background: "#1e293b",
              color: "#94a3b8",
              border: "1px solid #334155",
              cursor: "pointer",
              fontSize: "13px",
            },
          },
          "Refresh"
        )
      ),

      // Receipts panel
      h(ReceiptsPanel, null)
    );
  }

  // Register with the host
  PLUGINS.register("nunchi", NunchiPanel);
})();
