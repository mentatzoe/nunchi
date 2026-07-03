/**
 * Nunchi Gate Dashboard Tab
 *
 * Plain-JS IIFE — no build step required.  Runs in the Hermes dashboard host
 * page, which exposes React and UI components on window.__HERMES_PLUGIN_SDK__
 * and registers plugins via window.__HERMES_PLUGINS__.register().
 *
 * Design: all colours and fonts via host CSS custom properties (var(--...))
 * and SDK components from window.__HERMES_PLUGIN_SDK__.components.
 * Zero hardcoded hex literals or font names.
 *
 * Features:
 *   - Channel display names from channel_directory.json (enriched by plugin_api).
 *   - Native look via SDK Card, Button, Input, Label, Select, Badge, Tabs, Separator.
 *   - Per-channel and global Settings: senders (with allow_from editor when
 *     allowlist), verbosity, model, pinned_rules — all with inline help text
 *     and provenance badges.
 *   - Receipts panel: pause/resume, interval select, visibility-suspend,
 *     verdict legend (4 distinct entries), confidence distribution per row.
 *   - All prior patch semantics preserved: apply_state_patch (empty-dict clears,
 *     null deletes, baseline-equal pruning), pending badges, unsaved-changes
 *     Save gating, auto-dismissing success messages, aria-hidden badges.
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
  var useRef = SDK.hooks.useRef;
  var fetchJSON = SDK.fetchJSON;
  var h = React.createElement;

  // SDK UI components — every visual element goes through these or CSS vars.
  var C = SDK.components;
  var SDKCard = C.Card;
  var SDKCardHeader = C.CardHeader;
  var SDKCardTitle = C.CardTitle;
  var SDKCardContent = C.CardContent;
  var SDKBadge = C.Badge;
  var SDKButton = C.Button;
  var SDKInput = C.Input;
  var SDKLabel = C.Label;
  var SDKSelect = C.Select;
  var SDKSelectOption = C.SelectOption;
  var SDKSeparator = C.Separator;
  var SDKTabs = C.Tabs;
  var SDKTabsList = C.TabsList;
  var SDKTabsTrigger = C.TabsTrigger;

  // -------------------------------------------------------------------------
  // Constants
  // -------------------------------------------------------------------------
  var API_BASE = "/api/plugins/nunchi";
  var SENDERS_OPTIONS = ["all", "humans", "allowlist"];
  var VERBOSITY_OPTIONS = ["minimal", "normal", "debug"];
  var POLL_INTERVALS = [
    { label: "2 s", value: 2000 },
    { label: "5 s", value: 5000 },
    { label: "15 s", value: 15000 },
    { label: "Off", value: 0 },
  ];
  var SUCCESS_DISMISS_MS = 4000;
  var LS_POLL_KEY = "nunchi.poll";

  // -------------------------------------------------------------------------
  // Owner-mandated help copy (verbatim)
  // -------------------------------------------------------------------------
  var HELP = {
    senders_all:
      "Every message in this channel is judged by the gate.",
    senders_humans:
      "Only human messages are judged; messages from other bots are dropped before the gate — no reply, no cost.",
    senders_allowlist:
      "Only the senders listed below are judged; everyone else is dropped silently.",
    verbosity_minimal:
      "Receipts record verdict and action only.",
    verbosity_normal:
      "Adds author, history size, reasons, and the confidence distribution.",
    verbosity_debug:
      "Adds the full gate payload and response — for troubleshooting.",
    pinned_rules:
      "Governance text the gate applies with precedence over plain social sense — e.g. a strict open-floor doctrine. This shapes the GATE’s judgment; it does not change the agent’s persona.",
  };

  // -------------------------------------------------------------------------
  // Textarea style — reused for allow_from and pinned_rules
  // -------------------------------------------------------------------------
  var TEXTAREA_STYLE = {
    width: "100%",
    boxSizing: "border-box",
    background: "transparent",
    border: "1px solid color-mix(in srgb, var(--midground-base) 15%, transparent)",
    borderRadius: "var(--theme-radius, 4px)",
    color: "var(--color-text-primary)",
    fontFamily: "var(--theme-font-mono)",
    fontSize: "12px",
    padding: "6px 8px",
    resize: "vertical",
    outline: "none",
    lineHeight: "1.5",
  };

  // -------------------------------------------------------------------------
  // Utility: receipt timestamp — date-aware (mn2)
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
  // Utility: provenance badge using SDK Badge
  // pendingCh/pendingGl checked BEFORE saved-provenance (M2).
  // A null value in pending counts as a pending edit (it is the deletion
  // signal for a key); undefined values are treated as "no pending change".
  // aria-hidden="true" so badge text is not read as part of accessible name (M4).
  // -------------------------------------------------------------------------
  function makeProvBadge(key, chOverrides, globalOverrides, pendingCh, pendingGl) {
    if (pendingCh && pendingCh[key] !== undefined)
      return h(SDKBadge, { tone: "warning", "aria-hidden": "true" }, "pending");
    if (pendingGl && pendingGl[key] !== undefined)
      return h(SDKBadge, { tone: "warning", "aria-hidden": "true" }, "pending");
    if (chOverrides && key in chOverrides)
      return h(SDKBadge, { "aria-hidden": "true" }, "channel");
    if (globalOverrides && key in globalOverrides)
      return h(SDKBadge, { tone: "secondary", "aria-hidden": "true" }, "global");
    return null;
  }

  // -------------------------------------------------------------------------
  // HelpText: small muted paragraph beneath a control
  // -------------------------------------------------------------------------
  function HelpText(props) {
    return h("p", {
      style: {
        fontSize: "11px",
        color: "var(--color-text-tertiary)",
        margin: "2px 0 0 0",
        lineHeight: "1.45",
      },
    }, props.children);
  }

  // -------------------------------------------------------------------------
  // SectionDivider: labelled horizontal rule matching Hermes ConfigPage style
  // -------------------------------------------------------------------------
  function SectionDivider(props) {
    return h(
      "div",
      {
        style: {
          display: "flex",
          alignItems: "center",
          gap: "8px",
          margin: "4px 0 10px 0",
        },
      },
      h("span", {
        style: {
          fontSize: "10px",
          fontWeight: "600",
          color: "var(--color-text-tertiary)",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        },
      }, props.label),
      h("div", {
        style: {
          flex: 1,
          height: "1px",
          background: "color-mix(in srgb, var(--midground-base) 10%, transparent)",
        },
      })
    );
  }

  // -------------------------------------------------------------------------
  // FieldRow: label + control + provenance badge + help text
  // -------------------------------------------------------------------------
  function FieldRow(props) {
    return h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "3px" } },
      h(
        "div",
        { style: { display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" } },
        props.badge || null,
        props.label
          ? h(
              SDKLabel,
              {
                htmlFor: props.id,
                style: {
                  fontSize: "12px",
                  color: "var(--color-text-secondary)",
                  minWidth: props.labelWidth || "auto",
                },
              },
              props.label
            )
          : null,
        props.control
      ),
      props.help ? h(HelpText, null, props.help) : null
    );
  }

  // -------------------------------------------------------------------------
  // GlobalCard: global override settings
  // -------------------------------------------------------------------------
  function GlobalCard(props) {
    var globalOv = props.globalOverrides || {};
    var pendingGl = props.pendingGlobal || {};

    var sendersVal = pendingGl.senders !== undefined
      ? (pendingGl.senders || "")
      : (globalOv.senders || "");
    var verbosityVal = pendingGl.verbosity !== undefined
      ? (pendingGl.verbosity || "")
      : (globalOv.verbosity || "");
    var modelVal = pendingGl.model !== undefined
      ? (pendingGl.model || "")
      : (globalOv.model || "");

    return h(
      SDKCard,
      { style: { marginBottom: "16px" } },
      h(
        SDKCardHeader,
        { className: "py-3 px-4" },
        h(SDKCardTitle, { className: "text-sm" }, "Global Overrides")
      ),
      h(
        SDKCardContent,
        { className: "px-4 pb-4 pt-3" },
        h(
          "div",
          { style: { display: "flex", flexDirection: "column", gap: "12px" } },

          // senders
          h(FieldRow, {
            label: "senders",
            badge: makeProvBadge("senders", null, globalOv, null, pendingGl),
            help: sendersVal ? (HELP["senders_" + sendersVal] || null) : null,
            control: h(SDKSelect, {
              value: sendersVal,
              onValueChange: function (v) { props.onChange("senders", v || undefined); },
              placeholder: "(inherit)",
            },
              h(SDKSelectOption, { value: "" }, "(inherit)"),
              SENDERS_OPTIONS.map(function (o) {
                return h(SDKSelectOption, { key: o, value: o }, o);
              })
            ),
          }),

          // verbosity
          h(FieldRow, {
            label: "verbosity",
            badge: makeProvBadge("verbosity", null, globalOv, null, pendingGl),
            help: verbosityVal ? (HELP["verbosity_" + verbosityVal] || null) : null,
            control: h(SDKSelect, {
              value: verbosityVal,
              onValueChange: function (v) { props.onChange("verbosity", v || undefined); },
              placeholder: "(inherit)",
            },
              h(SDKSelectOption, { value: "" }, "(inherit)"),
              VERBOSITY_OPTIONS.map(function (o) {
                return h(SDKSelectOption, { key: o, value: o }, o);
              })
            ),
          }),

          // model
          h(FieldRow, {
            label: "model",
            labelWidth: "52px",
            badge: makeProvBadge("model", null, globalOv, null, pendingGl),
            control: h(SDKInput, {
              type: "text",
              value: modelVal,
              onChange: function (e) { props.onChange("model", e.target.value || undefined); },
              placeholder: "default (from env)",
              style: { fontSize: "12px", height: "32px", flex: "1" },
            }),
          })
        )
      )
    );
  }

  // -------------------------------------------------------------------------
  // ChannelCard: per-channel settings
  // -------------------------------------------------------------------------
  function ChannelCard(props) {
    var cid = props.cid;
    var displayName = props.displayName;
    var eff = props.effective || {};
    var chOv = props.chOverrides || {};
    var globalOv = props.globalOverrides || {};
    var pendingCh = props.pendingCh || {};
    var isIntroduced = props.isIntroduced;
    var isNull = props.effective === null;

    var _pinnedOpen = useState(false);
    var pinnedOpen = _pinnedOpen[0];
    var setPinnedOpen = _pinnedOpen[1];

    var sendersEff = pendingCh.senders !== undefined
      ? (pendingCh.senders || "all")
      : (eff.senders || "all");

    // allow_from: pending value or effective value, displayed as newline-separated text
    var allowFromRaw = pendingCh.allow_from !== undefined
      ? pendingCh.allow_from
      : (eff.allow_from || []);
    var allowFromText = Array.isArray(allowFromRaw)
      ? allowFromRaw.join("\n")
      : String(allowFromRaw || "");

    var verbosityEff = pendingCh.verbosity !== undefined
      ? (pendingCh.verbosity || "normal")
      : (eff.verbosity || "normal");

    var modelEff = pendingCh.model !== undefined
      ? (pendingCh.model || "")
      : (eff.model || "");

    var pinnedRulesEff = pendingCh.pinned_rules !== undefined
      ? (pendingCh.pinned_rules || "")
      : (eff.pinned_rules || "");

    function handleChange(key, value) {
      props.onChange(cid, key, value);
    }

    return h(
      SDKCard,
      { style: { marginBottom: "10px" } },
      // Channel header
      h(
        SDKCardHeader,
        { className: "py-3 px-4" },
        h(
          "div",
          { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
          h(
            "div",
            { style: { flex: 1, minWidth: 0 } },
            displayName
              ? h("div", {
                  style: {
                    fontWeight: "600",
                    fontSize: "13px",
                    color: "var(--color-text-primary)",
                    marginBottom: "2px",
                  },
                }, displayName)
              : null,
            h("code", {
              style: {
                fontSize: "11px",
                color: "var(--color-text-tertiary)",
                fontFamily: "var(--theme-font-mono)",
              },
            }, cid)
          ),
          isIntroduced
            ? h(SDKBadge, { tone: "secondary" }, "state-introduced")
            : null,
          isNull
            ? h(SDKBadge, { tone: "destructive" }, "not gated")
            : null
        )
      ),
      // Channel body
      isNull
        ? h(
            SDKCardContent,
            { className: "px-4 pb-3 pt-2" },
            h(HelpText, null, "Disabled by state or not matched by config.yaml")
          )
        : h(
            SDKCardContent,
            { className: "px-4 pb-4 pt-3" },
            h(
              "div",
              { style: { display: "flex", flexDirection: "column", gap: "12px" } },

              // enabled
              h(FieldRow, {
                label: "enabled",
                badge: makeProvBadge("enabled", chOv, globalOv, pendingCh, null),
                control: h(SDKSelect, {
                  value: String(eff.enabled !== false),
                  onValueChange: function (v) { handleChange("enabled", v === "true"); },
                },
                  h(SDKSelectOption, { value: "true" }, "true"),
                  h(SDKSelectOption, { value: "false" }, "false")
                ),
              }),

              // senders
              h(FieldRow, {
                label: "senders",
                badge: makeProvBadge("senders", chOv, globalOv, pendingCh, null),
                help: HELP["senders_" + sendersEff] || HELP.senders_all,
                control: h(SDKSelect, {
                  value: sendersEff,
                  onValueChange: function (v) { handleChange("senders", v); },
                },
                  SENDERS_OPTIONS.map(function (o) {
                    return h(SDKSelectOption, { key: o, value: o }, o);
                  })
                ),
              }),

              // allow_from (revealed when senders=allowlist)
              sendersEff === "allowlist"
                ? h(
                    "div",
                    { style: { display: "flex", flexDirection: "column", gap: "4px" } },
                    h(
                      SDKLabel,
                      { style: { fontSize: "12px", color: "var(--color-text-secondary)" } },
                      "allow_from"
                    ),
                    h("textarea", {
                      value: allowFromText,
                      onChange: function (e) {
                        var lines = e.target.value
                          .split(/[\n,]+/)
                          .map(function (s) { return s.trim(); })
                          .filter(Boolean);
                        handleChange("allow_from", lines);
                      },
                      placeholder: "user_name or user_id\none per line or comma-separated",
                      rows: 3,
                      style: TEXTAREA_STYLE,
                    })
                  )
                : null,

              // verbosity
              h(FieldRow, {
                label: "verbosity",
                badge: makeProvBadge("verbosity", chOv, globalOv, pendingCh, null),
                help: HELP["verbosity_" + verbosityEff] || HELP.verbosity_normal,
                control: h(SDKSelect, {
                  value: verbosityEff,
                  onValueChange: function (v) { handleChange("verbosity", v); },
                },
                  VERBOSITY_OPTIONS.map(function (o) {
                    return h(SDKSelectOption, { key: o, value: o }, o);
                  })
                ),
              }),

              // model
              h(FieldRow, {
                label: "model",
                labelWidth: "52px",
                badge: makeProvBadge("model", chOv, globalOv, pendingCh, null),
                control: h(SDKInput, {
                  type: "text",
                  value: modelEff,
                  onChange: function (e) { handleChange("model", e.target.value || null); },
                  placeholder: eff.model || "inherit",
                  style: { fontSize: "12px", height: "32px", flex: "1" },
                }),
              }),

              // pinned_rules — collapsible
              h(
                "div",
                { style: { display: "flex", flexDirection: "column", gap: "4px" } },
                h(
                  "button",
                  {
                    type: "button",
                    onClick: function () { setPinnedOpen(!pinnedOpen); },
                    style: {
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      padding: "0",
                      color: "var(--color-text-secondary)",
                      fontSize: "12px",
                      textAlign: "left",
                      fontFamily: "var(--theme-font-sans)",
                    },
                  },
                  h("span", {
                    "aria-hidden": "true",
                    style: {
                      display: "inline-block",
                      transform: pinnedOpen ? "rotate(90deg)" : "rotate(0deg)",
                      transition: "transform 0.15s ease",
                      fontSize: "8px",
                    },
                  }, "►"),
                  "Room governance (pinned rules)",
                  makeProvBadge("pinned_rules", chOv, globalOv, pendingCh, null)
                ),
                pinnedOpen
                  ? h(
                      "div",
                      { style: { display: "flex", flexDirection: "column", gap: "4px", paddingLeft: "14px" } },
                      h(HelpText, null, HELP.pinned_rules),
                      h("textarea", {
                        value: pinnedRulesEff,
                        onChange: function (e) { handleChange("pinned_rules", e.target.value || null); },
                        placeholder: "Paste governance text here…",
                        rows: 4,
                        style: Object.assign({}, TEXTAREA_STYLE, {
                          fontFamily: "var(--theme-font-sans)",
                          marginTop: "4px",
                        }),
                      })
                    )
                  : null
              )
            )
          )
    );
  }

  // -------------------------------------------------------------------------
  // ReceiptsPanel: polls GET /receipts with polling controls
  // -------------------------------------------------------------------------
  function ReceiptsPanel() {
    // Load persisted poll settings from localStorage
    var defaultPoll = { paused: false, interval: 5000 };
    try {
      var saved = localStorage.getItem(LS_POLL_KEY);
      if (saved) {
        var parsed = JSON.parse(saved);
        if (typeof parsed.paused === "boolean") defaultPoll.paused = parsed.paused;
        if (typeof parsed.interval === "number") defaultPoll.interval = parsed.interval;
      }
    } catch (_) {}

    var _receipts = useState([]);
    var receipts = _receipts[0], setReceipts = _receipts[1];

    var _err = useState(null);
    var err = _err[0], setErr = _err[1];

    var _paused = useState(defaultPoll.paused);
    var paused = _paused[0], setPaused = _paused[1];

    var _interval = useState(defaultPoll.interval);
    var pollInterval = _interval[0], setPollInterval = _interval[1];

    var _hidden = useState(document.hidden);
    var isHidden = _hidden[0], setIsHidden = _hidden[1];

    // Persist poll settings
    useEffect(function () {
      try {
        localStorage.setItem(LS_POLL_KEY, JSON.stringify({ paused: paused, interval: pollInterval }));
      } catch (_) {}
    }, [paused, pollInterval]);

    // Suspend polling when document is hidden (visibilitychange); resume on show
    useEffect(function () {
      function onVis() { setIsHidden(document.hidden); }
      document.addEventListener("visibilitychange", onVis);
      return function () { document.removeEventListener("visibilitychange", onVis); };
    }, []);

    var poll = useCallback(function () {
      fetchJSON(API_BASE + "/receipts?limit=50")
        .then(function (data) {
          setReceipts(data.receipts || []);
          setErr(null);
        })
        .catch(function (e) { setErr(String(e)); });
    }, []);

    // Polling effect — starts fresh whenever paused/hidden/interval changes
    useEffect(function () {
      if (paused || isHidden || pollInterval === 0) return;
      poll();
      var id = setInterval(poll, pollInterval);
      return function () { clearInterval(id); };
    }, [poll, paused, isHidden, pollInterval]);

    // Badge tone for verdict chips, using host semantic tokens
    function verdictTone(verdict) {
      if (verdict === "PASS") return "destructive"; // suppressed = danger
      if (verdict === "SPEAK") return "success";    // full turn = go
      if (verdict === "ASK") return "warning";      // question = amber
      return "secondary";                            // ACK = neutral
    }

    var currentIntervalLabel = (POLL_INTERVALS.find(function (pi) {
      return pi.value === pollInterval;
    }) || { label: "?" }).label;

    return h(
      SDKCard,
      null,
      // Panel header with polling controls
      h(
        SDKCardHeader,
        { className: "py-3 px-4" },
        h(
          "div",
          { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
          h(SDKCardTitle, { className: "text-sm", style: { flex: "1" } },
            "Gate Receipts (newest first)"
          ),
          // Interval select
          h(SDKSelect, {
            value: String(pollInterval),
            onValueChange: function (v) { setPollInterval(parseInt(v, 10)); },
          },
            POLL_INTERVALS.map(function (pi) {
              return h(SDKSelectOption, { key: pi.value, value: String(pi.value) }, pi.label);
            })
          ),
          // Pause/resume
          h(SDKButton, {
            size: "sm",
            ghost: true,
            outlined: paused,
            onClick: function () { setPaused(!paused); },
            title: paused ? "Resume polling" : "Pause polling",
          }, paused ? "► Resume" : "⏸ Pause"),
          // Status badge
          isHidden
            ? h(SDKBadge, { tone: "secondary" }, "suspended")
            : (paused
                ? h(SDKBadge, { tone: "warning" }, "paused")
                : (pollInterval === 0
                    ? h(SDKBadge, { tone: "secondary" }, "off")
                    : h(SDKBadge, { tone: "secondary" }, "polling " + currentIntervalLabel)))
        )
      ),
      h(
        SDKCardContent,
        { className: "px-4 pb-4 pt-2" },
        // Verdict legend — 4 distinct entries (corrected from previous 3-entry version)
        h(
          "div",
          {
            style: {
              display: "flex",
              gap: "8px",
              flexWrap: "wrap",
              alignItems: "center",
              paddingBottom: "10px",
              marginBottom: "10px",
              borderBottom: "1px solid color-mix(in srgb, var(--midground-base) 10%, transparent)",
            },
          },
          h(SDKBadge, { tone: "destructive" }, "PASS"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } },
            "= suppressed (no message)"),
          h("span", { style: { color: "var(--color-text-tertiary)" } }, "·"),
          h(SDKBadge, { tone: "secondary" }, "ACK"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } },
            "= brief presence signal"),
          h("span", { style: { color: "var(--color-text-tertiary)" } }, "·"),
          h(SDKBadge, { tone: "warning" }, "ASK"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } },
            "= one clarifying question"),
          h("span", { style: { color: "var(--color-text-tertiary)" } }, "·"),
          h(SDKBadge, { tone: "success" }, "SPEAK"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } },
            "= full turn")
        ),
        // Receipt rows
        err
          ? h("p", { style: { color: "var(--color-destructive)", fontSize: "12px", margin: 0 } }, err)
          : receipts.length === 0
          ? h("p", { style: { color: "var(--color-text-tertiary)", fontSize: "12px", margin: 0 } },
              "No receipts yet.")
          : h(
              "div",
              {
                style: {
                  maxHeight: "420px",
                  overflowY: "auto",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                },
              },
              receipts.map(function (r, i) {
                var verdict = r.verdict || r.action || "?";
                var displayVerdict = (verdict === "PASS" || r.action === "skip") ? "PASS" : verdict;

                // Confidences — sorted highest-first
                var confs = r.confidences;
                var confKeys = confs
                  ? Object.keys(confs).sort(function (a, b) { return confs[b] - confs[a]; })
                  : [];

                return h(
                  "div",
                  {
                    key: i,
                    style: {
                      padding: "8px 10px",
                      borderRadius: "var(--theme-radius, 4px)",
                      background: "color-mix(in srgb, var(--midground-base) 4%, transparent)",
                      border: "1px solid color-mix(in srgb, var(--midground-base) 8%, transparent)",
                      fontSize: "11px",
                      color: "var(--color-text-primary)",
                    },
                  },
                  // Row header: timestamp · verdict chip · author · channel (right-aligned)
                  h(
                    "div",
                    { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
                    h("span", { style: { color: "var(--color-text-tertiary)", minWidth: "80px", flexShrink: 0 } },
                      r.ts ? formatReceiptTs(r.ts) : ""),
                    h(SDKBadge, { tone: verdictTone(displayVerdict) },
                      displayVerdict === "PASS" ? "PASS (suppressed)" : displayVerdict),
                    r.trigger_author
                      ? h("span", { style: { color: "var(--color-text-secondary)" } },
                          "@" + r.trigger_author)
                      : null,
                    h("span", {
                      style: {
                        marginLeft: "auto",
                        color: "var(--color-text-tertiary)",
                        fontFamily: "var(--theme-font-mono)",
                        fontSize: "10px",
                      },
                    }, (r.channel_ids || []).join(", "))
                  ),
                  // Reasons — up to 3 joined with · (mn3)
                  r.reasons && r.reasons.length > 0
                    ? h("div", {
                        style: {
                          marginTop: "4px",
                          color: "var(--color-text-secondary)",
                          fontSize: "10px",
                        },
                      }, r.reasons.slice(0, 3).join(" · "))
                    : null,
                  // Confidence distribution — compact inline format + mini bar
                  confs && confKeys.length > 0
                    ? h(
                        "div",
                        { style: { marginTop: "6px" } },
                        // Text row: "SPEAK 0.70 · PASS 0.20 · …" with winner bold
                        h(
                          "div",
                          { style: { display: "flex", gap: "8px", flexWrap: "wrap", fontSize: "10px", marginBottom: "4px" } },
                          confKeys.map(function (k) {
                            var isWinner = k === displayVerdict;
                            return h(
                              "span",
                              {
                                key: k,
                                style: {
                                  fontWeight: isWinner ? "700" : "400",
                                  color: isWinner
                                    ? "var(--color-text-primary)"
                                    : "var(--color-text-tertiary)",
                                },
                              },
                              k + " " + (confs[k] !== undefined ? Number(confs[k]).toFixed(2) : "0.00")
                            );
                          })
                        ),
                        // Mini percentage bar for the winning verdict
                        h(
                          "div",
                          {
                            style: {
                              height: "3px",
                              width: "100%",
                              background: "color-mix(in srgb, var(--midground-base) 10%, transparent)",
                              borderRadius: "2px",
                              overflow: "hidden",
                            },
                          },
                          h("div", {
                            style: {
                              height: "100%",
                              width: Math.round(((confs[confKeys[0]] || 0) * 100)) + "%",
                              background: confKeys[0] === "SPEAK" ? "var(--color-success)"
                                : confKeys[0] === "PASS" ? "var(--color-destructive)"
                                : confKeys[0] === "ASK" ? "var(--color-warning)"
                                : "var(--color-text-secondary)",
                              transition: "width 0.3s ease",
                            },
                          })
                        )
                      )
                    : null
                );
              })
            )
      )
    );
  }

  // -------------------------------------------------------------------------
  // Main plugin component
  // -------------------------------------------------------------------------
  function NunchiPanel() {
    var _stateData = useState({ baseline: {}, overrides: {}, effective: {}, channel_names: {} });
    var stateData = _stateData[0], setStateData = _stateData[1];

    var _pending = useState({});
    var pending = _pending[0], setPending = _pending[1];

    var _status = useState(null);
    var status = _status[0], setStatus = _status[1];

    var _loading = useState(true);
    var loading = _loading[0], setLoading = _loading[1];

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
    // are pruned.  Complex types (lists) skip the equality check — server B2b
    // handles deduplication.
    var handleChannelChange = useCallback(
      function (cid, key, value) {
        setPending(function (prev) {
          var channels = Object.assign({}, prev.channels || {});
          var ch = Object.assign({}, channels[cid] || {});

          // Resolve baseline value for this key+channel.
          var baseline = stateData.baseline || {};
          var baselineChs = baseline.channels || baseline.channel_ids;
          var chCfg = {};
          if (baselineChs && typeof baselineChs === "object" && !Array.isArray(baselineChs)) {
            chCfg = baselineChs[cid] || {};
          }
          var baselineVal = key in chCfg ? chCfg[key] : baseline[key];

          // Coerce enabled string from select to bool.
          var coerced = key === "enabled" ? value === "true" : value;

          // Lists skip equality check (reference inequality always); server prunes B2b.
          if (Array.isArray(coerced)) {
            ch[key] = coerced;
          } else {
            // null means "deletion signal" — pass through; empty string treated as null.
            if (coerced === "" && (key === "model" || key === "pinned_rules")) {
              coerced = null;
            }
            ch[key] = coerced === baselineVal ? null : coerced;
          }

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
    var channelNames = stateData.channel_names || {};

    var pendingGlobal = pending.global || {};
    var pendingChannels = pending.channels || {};
    var allCids = Array.from(
      new Set(Object.keys(effective).concat(Object.keys(pendingChannels)))
    ).sort();

    // Determine state-introduced channels (absent from baseline channels).
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

    var isError = status && (status.indexOf("failed") !== -1 || status.indexOf("Error") !== -1);

    // Settings tab content (extracted for clarity)
    function SettingsContent() {
      return h(
        "div",
        null,
        h(GlobalCard, {
          globalOverrides: globalOv,
          pendingGlobal: pendingGlobal,
          onChange: handleGlobalChange,
        }),
        h(SectionDivider, { label: "Channels" }),
        allCids.length === 0
          ? h("p", { style: { fontSize: "12px", color: "var(--color-text-tertiary)", margin: 0 } },
              "No channels configured.")
          : allCids.map(function (cid) {
              var eff = effective[cid] !== undefined ? effective[cid] : null;
              // Merge pending channel overrides into effective display
              var displayEff = eff;
              if (eff && pendingChannels[cid]) {
                displayEff = Object.assign({}, eff, pendingChannels[cid]);
              }
              return h(ChannelCard, {
                key: cid,
                cid: cid,
                displayName: channelNames[cid] || null,
                effective: displayEff,
                chOverrides: chStates[cid] || {},
                globalOverrides: globalOv,
                pendingCh: pendingChannels[cid] || {},
                isIntroduced: !baselineChannels[cid],
                baseline: stateData.baseline || {},
                onChange: handleChannelChange,
              });
            })
      );
    }

    return h(
      "div",
      {
        style: {
          padding: "1rem 1.5rem",
          maxWidth: "56rem",
          fontFamily: "var(--theme-font-sans)",
          color: "var(--color-text-primary)",
        },
      },

      // Page header
      h(
        "div",
        { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" } },
        h("h2", {
          style: {
            fontSize: "14px",
            fontWeight: "700",
            margin: 0,
            color: "var(--midground)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
          },
        }, "Nunchi Gate"),
        loading
          ? h("span", { style: { fontSize: "12px", color: "var(--color-text-tertiary)" } }, "Loading…")
          : null,
        status
          ? h("span", {
              style: {
                fontSize: "12px",
                color: isError ? "var(--color-destructive)" : "var(--color-success)",
              },
            }, status)
          : null
      ),

      // Action bar
      h(
        "div",
        {
          style: {
            display: "flex",
            gap: "8px",
            alignItems: "center",
            marginBottom: "20px",
            flexWrap: "wrap",
          },
        },
        h(SDKButton, {
          size: "sm",
          disabled: !hasPending,
          title: hasPending ? undefined : "No unsaved changes",
          onClick: save,
        }, "Save"),
        // M3: amber "Unsaved changes" indicator
        hasPending
          ? h("span", {
              style: {
                fontSize: "12px",
                color: "var(--color-warning)",
                fontWeight: "600",
              },
            }, "Unsaved changes")
          : null,
        h(SDKButton, {
          size: "sm",
          ghost: true,
          onClick: load,
        }, "Refresh"),
        h(SDKButton, {
          size: "sm",
          ghost: true,
          destructive: true,
          onClick: resetAll,
        }, "Reset All Overrides")
      ),

      // Tabs: Settings | Receipts
      h(SDKTabs, {
        defaultValue: "settings",
      },
        function (activeTab, setActiveTab) {
          return h(
            "div",
            { style: { display: "flex", flexDirection: "column", gap: "16px" } },
            h(
              SDKTabsList,
              null,
              h(SDKTabsTrigger, {
                value: "settings",
                active: activeTab === "settings",
                onClick: function () { setActiveTab("settings"); },
              }, "Settings"),
              h(SDKTabsTrigger, {
                value: "receipts",
                active: activeTab === "receipts",
                onClick: function () { setActiveTab("receipts"); },
              }, "Receipts")
            ),
            activeTab === "settings"
              ? h(SettingsContent, null)
              : h(ReceiptsPanel, null)
          );
        }
      )
    );
  }

  // Register with the host
  PLUGINS.register("nunchi", NunchiPanel);
})();
