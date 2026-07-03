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
 *   - Save button (PUT /api/plugins/nunchi/state) — disabled when no pending
 *     changes, with amber "Unsaved changes" indicator when edits exist (M3).
 *   - Reset-overrides button (PUT with empty global+channels, now correctly
 *     clears state via replace-empty semantics — B1).
 *   - Receipts panel (GET /api/plugins/nunchi/receipts) polling every 5 s.
 *
 * Patch semantics (B1, B2):
 *   - An empty {} for "global" or "channels" REPLACES (clears) that section.
 *   - A null value for any per-channel override key is a deletion signal that
 *     removes that key from stored overrides.
 *   - When a user selects the same value as the static baseline, null is sent
 *     so the server prunes the redundant override (B2).
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
  var SUCCESS_DISMISS_MS = 4000;

  // -------------------------------------------------------------------------
  // Utility: provenance badge
  // M4: aria-hidden="true" on the span so badge text is not read as part of
  //     the field's accessible name.
  // M2: pendingCh/pendingGl checked BEFORE saved-provenance so a pending edit
  //     shows amber "pending" rather than the stale saved-provenance badge.
  // -------------------------------------------------------------------------
  function Badge(text, color) {
    return h(
      "span",
      {
        "aria-hidden": "true",
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

  // pendingCh / pendingGl are optional; pass null when not applicable.
  // A null value in pending counts as a pending edit (it is the deletion
  // signal for a key); undefined values are treated as "no pending change".
  function provenanceBadge(key, chOverrides, globalOverrides, pendingCh, pendingGl) {
    if (pendingCh && pendingCh[key] !== undefined)
      return Badge("pending", "#d97706");
    if (pendingGl && pendingGl[key] !== undefined)
      return Badge("pending", "#d97706");
    if (chOverrides && key in chOverrides)
      return Badge("channel-override", "#7c3aed");
    if (globalOverrides && key in globalOverrides)
      return Badge("global-override", "#0369a1");
    return null;
  }

  // -------------------------------------------------------------------------
  // Utility: receipt timestamp
  // mn2: show date for receipts not from today.
  // -------------------------------------------------------------------------
  function formatReceiptTs(ts) {
    var d = new Date(ts * 1000);
    var now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString();
    }
    return d.toLocaleDateString() + " " + d.toLocaleTimeString();
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
    var pendingCh = props.pendingCh || {};

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
              badge: provenanceBadge("enabled", chOv, globalOv, pendingCh, null),
            }),
            h(SelectField, {
              label: "senders",
              value: eff.senders || "all",
              options: SENDERS_OPTIONS,
              onChange: function (v) { props.onChange(cid, "senders", v); },
              badge: provenanceBadge("senders", chOv, globalOv, pendingCh, null),
            }),
            h(SelectField, {
              label: "verbosity",
              value: eff.verbosity || "normal",
              options: VERBOSITY_OPTIONS,
              onChange: function (v) { props.onChange(cid, "verbosity", v); },
              badge: provenanceBadge("verbosity", chOv, globalOv, pendingCh, null),
            })
          )
    );
  }

  // -------------------------------------------------------------------------
  // ReceiptsPanel: polls GET /receipts every 5 s
  // p1: "PASS (suppressed)" label + one-line legend.
  // mn2: date-aware timestamp (via formatReceiptTs).
  // mn3: up to 3 reasons joined with " · ".
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
        { style: { fontSize: "13px", fontWeight: "600", color: "#94a3b8", marginBottom: "4px" } },
        "Gate Receipts (newest first, polling every 5 s)"
      ),
      // p1: legend under heading
      h(
        "p",
        { style: { fontSize: "10px", color: "#64748b", margin: "0 0 8px 0" } },
        "PASS = suppressed · SPEAK = full turn · ACK/ASK = brief turn"
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
              // p1: annotate PASS to make suppression semantics explicit.
              var displayVerdict =
                verdict === "PASS" || r.action === "skip"
                  ? "PASS (suppressed)"
                  : verdict;
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
                // mn2: date-aware timestamp
                h("span", { style: { opacity: 0.7, minWidth: "80px" } },
                  r.ts ? formatReceiptTs(r.ts) : ""),
                h("span", { style: { fontWeight: "700", minWidth: "72px" } }, displayVerdict),
                h("span", { style: { opacity: 0.8 } },
                  r.trigger_author ? ("@" + r.trigger_author + " ") : ""),
                // mn3: up to 3 reasons joined with " · "
                r.reasons && r.reasons.length > 0
                  ? h("span", { style: { opacity: 0.7, fontSize: "10px" } },
                      r.reasons.slice(0, 3).join(" · "))
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

    // B2: when the selected value equals the static baseline value for that
    // field, send null (the server-side deletion signal) so redundant overrides
    // are pruned.  Uses the stateData closure so deps must include stateData.
    var handleChannelChange = useCallback(
      function (cid, key, value) {
        setPending(function (prev) {
          var channels = Object.assign({}, prev.channels || {});
          var ch = Object.assign({}, channels[cid] || {});

          // Resolve baseline value for this key+channel from the static config.
          // Map form: baseline.channels[cid][key]; list form: no per-channel
          // config, so fall back to top-level baseline key.
          var baseline = stateData.baseline || {};
          var baselineChs = baseline.channels || baseline.channel_ids;
          var chCfg = {};
          if (
            baselineChs &&
            typeof baselineChs === "object" &&
            !Array.isArray(baselineChs)
          ) {
            chCfg = baselineChs[cid] || {};
          }
          var baselineVal = key in chCfg ? chCfg[key] : baseline[key];

          // Coerce the select string to the typed value used in effective config.
          var coerced = key === "enabled" ? value === "true" : value;

          // If the selected value matches the static baseline, send null so the
          // server's apply_state_patch prunes the now-redundant override.
          ch[key] = coerced === baselineVal ? null : coerced;

          channels[cid] = ch;
          return Object.assign({}, prev, { channels: channels });
        });
      },
      [stateData]
    );

    var handleGlobalChange = useCallback(
      function (key, value) {
        setPending(function (prev) {
          var g = Object.assign({}, prev.global || {});
          g[key] = value || undefined;
          return Object.assign({}, prev, { global: g });
        });
      },
      []
    );

    // M1: auto-dismiss success status after 4 s; error messages persist.
    function setSuccessStatus(msg) {
      setStatus(msg);
      setTimeout(function () {
        setStatus(function (prev) { return prev === msg ? null : prev; });
      }, SUCCESS_DISMISS_MS);
    }

    var save = useCallback(
      function () {
        fetchJSON(API_BASE + "/state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pending),
        })
          .then(function () {
            setSuccessStatus("Saved.");
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
        // B1: empty dicts signal REPLACE (clear), not merge.
        fetchJSON(API_BASE + "/state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ global: {}, channels: {} }),
        })
          .then(function () {
            setSuccessStatus("All overrides cleared.");
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

    // Determine state-introduced channels (those absent from baseline channels).
    // p2: fall back to baseline.channel_ids when baseline.channels is absent.
    var baselineChannels = {};
    var baselineChs =
      stateData.baseline &&
      (stateData.baseline.channels || stateData.baseline.channel_ids);
    if (baselineChs && typeof baselineChs === "object" && !Array.isArray(baselineChs)) {
      Object.keys(baselineChs).forEach(function (k) {
        if (k !== "*") baselineChannels[k] = true;
      });
    } else if (Array.isArray(baselineChs)) {
      baselineChs.forEach(function (k) { baselineChannels[k] = true; });
    }

    // M3: compute whether there are any pending (unsaved) edits.
    // undefined values in pendingGlobal come from the empty-string select
    // option and are not real pending changes.  null values in channel pending
    // are deletion signals and ARE real pending changes.
    var hasPendingGlobal = Object.keys(pendingGlobal).some(function (k) {
      return pendingGlobal[k] !== undefined;
    });
    var hasPendingChannels = Object.keys(pendingChannels).some(function (cid) {
      var ch = pendingChannels[cid] || {};
      return Object.keys(ch).length > 0;
    });
    var hasPending = hasPendingGlobal || hasPendingChannels;

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
          ? h(
              "span",
              {
                style: {
                  fontSize: "12px",
                  color: status.indexOf("failed") !== -1 || status.indexOf("Error") !== -1
                    ? "#f87171"
                    : "#38bdf8",
                },
              },
              status
            )
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
          badge: provenanceBadge("senders", null, globalOv, null, pendingGlobal),
        }),
        h(SelectField, {
          label: "verbosity",
          value: pendingGlobal.verbosity || globalOv.verbosity || "",
          options: ["", "minimal", "normal", "debug"],
          onChange: function (v) {
            handleGlobalChange("verbosity", v || undefined);
          },
          badge: provenanceBadge("verbosity", null, globalOv, null, pendingGlobal),
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
                pendingCh: pendingChannels[cid] || {},
                isIntroduced: !baselineChannels[cid],
                onChange: handleChannelChange,
              });
            })
      ),

      // Action buttons + M3 unsaved-changes indicator
      h(
        "div",
        { style: { display: "flex", gap: "8px", alignItems: "center", marginBottom: "16px" } },
        h(
          "button",
          {
            onClick: save,
            disabled: !hasPending,
            title: hasPending ? undefined : "No unsaved changes",
            style: {
              padding: "6px 16px",
              borderRadius: "6px",
              background: hasPending ? "#2563eb" : "#1e3a5f",
              color: "#fff",
              border: "none",
              cursor: hasPending ? "pointer" : "not-allowed",
              fontSize: "13px",
              fontWeight: "600",
              opacity: hasPending ? 1 : 0.5,
            },
          },
          "Save"
        ),
        // M3: amber "Unsaved changes" indicator shown only when hasPending
        hasPending
          ? h(
              "span",
              {
                style: {
                  fontSize: "12px",
                  color: "#d97706",
                  fontWeight: "600",
                },
              },
              "Unsaved changes"
            )
          : null,
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
