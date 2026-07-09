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
 *   - Add channel control: pick from directory or enter arbitrary ID; staged
 *     as channels.{id}.enabled=true through the normal Save flow.
 *   - Honest model display: resolved_model from API (config/environment/dotenv)
 *     shown as "currently: <value> (from <source>)" with caveat tooltip.
 *   - Receipts panel: pause/resume, interval select, visibility-suspend,
 *     verdict legend (4 distinct entries), confidence distribution per row.
 *   - Expandable receipt rows: click to reveal full detail (all JSONL fields),
 *     including debug payload/directive when present.
 *   - All prior patch semantics preserved: apply_state_patch (empty-dict clears,
 *     null deletes, baseline-equal pruning), pending badges, unsaved-changes
 *     Save gating, auto-dismissing success messages, aria-hidden badges.
 *   - Silent-failure contract: PUT /state echoes applied_state + rejected_keys;
 *     JS diffs against sent keys and shows a persistent error on mismatch.
 *   - Version handshake: api_version in GET /state; banner when outdated.
 */
(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Idempotent registration guard — prevents double-mount when the retry
  // injection at the bottom of this block fires a second time.
  // -------------------------------------------------------------------------
  if (window.__NUNCHI_REGISTERED__) return;

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
  // Must match PLUGIN_API_VERSION in dashboard/plugin_api.py.
  var EXPECTED_API_VERSION = "3";

  var SENDERS_OPTIONS = ["all", "humans", "allowlist"];
  // Objects so the label carries the short meaning (finding 8).
  var VERBOSITY_OPTIONS = [
    { value: "minimal", label: "minimal — verdict & action only" },
    { value: "normal",  label: "normal — + reasons & confidences" },
    { value: "debug",   label: "debug — + full payload" },
  ];
  var POLL_INTERVALS = [
    { label: "2 s", value: 2000 },
    { label: "5 s", value: 5000 },
    { label: "15 s", value: 15000 },
    { label: "Off", value: 0 },
  ];
  var SUCCESS_DISMISS_MS = 4000;
  var LS_POLL_KEY = "nunchi.poll";

  // -------------------------------------------------------------------------
  // allow_from flush registry
  // Keys: channel-id.  Values: function() -> parsed lines | undefined.
  // Called by save() before building the patch so that save-without-blur
  // still picks up the latest raw text from each allowlist textarea.
  // -------------------------------------------------------------------------
  var _allowFromFlush = {};

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
      "Receipt log: verdict and action only. (Does not change the agent's replies.)",
    verbosity_normal:
      "Receipt log: adds author, history size, reasons, and confidences.",
    verbosity_debug:
      "Receipt log: adds the full gate payload and response — for troubleshooting.",
    pinned_rules:
      "Governance text the gate applies with precedence over plain social sense — e.g. a strict open-floor doctrine. This shapes the GATE's judgment; it does not change the agent's persona.",
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

  // Full locale date-time string for expanded receipt panel.
  function formatReceiptTsFull(ts) {
    return new Date(ts * 1000).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
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
    var base = {
      fontSize: "11px",
      color: "var(--color-text-tertiary, var(--color-text-secondary))",
      margin: "2px 0 0 0",
      lineHeight: "1.45",
    };
    if (props.style) {
      for (var k in props.style) { if (props.style.hasOwnProperty(k)) base[k] = props.style[k]; }
    }
    return h("p", { style: base }, props.children);
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
          color: "var(--color-text-tertiary, var(--color-text-secondary))",
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
  // Callers pass id so the SDKLabel's htmlFor associates with the control.
  // -------------------------------------------------------------------------
  function FieldRow(props) {
    // helpInline: render the help text beside the control (same row) instead of
    // on a line below — saves vertical space for short select descriptions.
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
        props.control,
        props.helpInline && props.help
          ? h(HelpText, { style: { margin: 0, flex: "1 1 12rem", minWidth: "10rem" } }, props.help)
          : null
      ),
      !props.helpInline && props.help ? h(HelpText, null, props.help) : null
    );
  }

  // -------------------------------------------------------------------------
  // resolvedModelLabel: format a {value, source} object for display.
  // The caveat — that this was computed by the dashboard service process, not
  // the gateway — is shown as a tooltip on the help text element.
  // -------------------------------------------------------------------------
  function resolvedModelLabel(resolvedModel) {
    if (!resolvedModel || !resolvedModel.value) return "(not configured)";
    var srcLabel = resolvedModel.source === "config"      ? "config"
                 : resolvedModel.source === "environment" ? "env var"
                 : resolvedModel.source === "dotenv"      ? ".env"
                 : "";
    return resolvedModel.value + (srcLabel ? " (from " + srcLabel + ")" : "");
  }

  var _MODEL_CAVEAT_TITLE =
    "Model resolution computed by the dashboard service process. " +
    "The gateway's environment is authoritative at gate time.";

  // -------------------------------------------------------------------------
  // AddChannelControl: "Add channel" section at the bottom of the Channels list
  // -------------------------------------------------------------------------
  function AddChannelControl(props) {
    var availableChannels = props.availableChannels || [];
    var onAdd = props.onAdd; // function(cid) -> stages channels.{cid}.enabled=true

    var _textVal = useState("");
    var textVal = _textVal[0];
    var setTextVal = _textVal[1];

    var _addErr = useState(null);
    var addErr = _addErr[0];
    var setAddErr = _addErr[1];

    // Validate a raw channel ID string.
    // Accept any non-empty token without spaces (don't enforce digits-only
    // since other platforms use non-numeric IDs).
    function _validate(raw) {
      var trimmed = (raw || "").trim();
      if (!trimmed) return { err: "Channel ID cannot be empty." };
      if (/\s/.test(trimmed)) return { err: "Channel ID must not contain spaces." };
      return { id: trimmed };
    }

    function handleSelectChange(v) {
      // Selecting from directory auto-fills the text input for confirmation.
      setTextVal(v || "");
      setAddErr(null);
    }

    function handleAdd() {
      var v = _validate(textVal);
      if (v.err) { setAddErr(v.err); return; }
      onAdd(v.id);
      setTextVal("");
      setAddErr(null);
    }

    function handleKeyDown(e) {
      if (e.key === "Enter") handleAdd();
    }

    return h(
      "div",
      {
        style: {
          border: "1px solid color-mix(in srgb, var(--midground-base) 12%, transparent)",
          borderRadius: "var(--theme-radius, 4px)",
          padding: "12px 14px",
          marginTop: "16px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        },
      },
      h("div", {
        style: {
          fontSize: "11px",
          fontWeight: "600",
          color: "var(--color-text-secondary)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        },
      }, "Add channel"),

      // Select: available channels from directory (when any exist)
      availableChannels.length > 0
        ? h(
            "div",
            { style: { display: "flex", flexDirection: "column", gap: "3px" } },
            h(SDKLabel, {
              htmlFor: "nunchi-add-ch-select",
              style: { fontSize: "12px", color: "var(--color-text-secondary)" },
            }, "From channel directory"),
            h(SDKSelect, {
              id: "nunchi-add-ch-select",
              value: "",
              onValueChange: handleSelectChange,
              placeholder: "— pick a channel to pre-fill —",
            },
              h(SDKSelectOption, { value: "" }, "— pick a channel to pre-fill —"),
              availableChannels.map(function (ch) {
                return h(SDKSelectOption, { key: ch.id, value: ch.id },
                  ch.name + "  (" + ch.id + ")");
              })
            )
          )
        : null,

      // Free-text input for arbitrary IDs
      h(
        "div",
        { style: { display: "flex", flexDirection: "column", gap: "3px" } },
        h(SDKLabel, {
          htmlFor: "nunchi-add-ch-text",
          style: { fontSize: "12px", color: "var(--color-text-secondary)" },
        }, availableChannels.length > 0 ? "Or enter channel ID directly" : "Channel ID"),
        h("div", { style: { display: "flex", gap: "6px" } },
          h(SDKInput, {
            id: "nunchi-add-ch-text",
            type: "text",
            value: textVal,
            onChange: function (e) { setTextVal(e.target.value); setAddErr(null); },
            onKeyDown: handleKeyDown,
            placeholder: "e.g. 1518384310321811456",
            style: { fontSize: "12px", height: "32px", flex: "1" },
          }),
          h(SDKButton, {
            size: "sm",
            disabled: !textVal.trim(),
            onClick: handleAdd,
          }, "Add")
        ),
        addErr
          ? h("p", {
              style: { fontSize: "11px", color: "var(--color-destructive)", margin: "2px 0 0 0" },
            }, addErr)
          : null
      ),

      // Inline help (verbatim per spec)
      h("p", {
        style: {
          fontSize: "11px",
          color: "var(--color-text-tertiary, var(--color-text-secondary))",
          margin: 0,
          lineHeight: "1.5",
        },
      },
        "Channels can also be added with ",
        h("code", {
          style: {
            fontFamily: "var(--theme-font-mono)", fontSize: "10px",
            background: "color-mix(in srgb, var(--midground-base) 8%, transparent)",
            borderRadius: "3px", padding: "0 3px",
          },
        }, "/nunchi enable <channel-id>"),
        " from chat, or permanently in config.yaml under ",
        h("code", {
          style: {
            fontFamily: "var(--theme-font-mono)", fontSize: "10px",
            background: "color-mix(in srgb, var(--midground-base) 8%, transparent)",
            borderRadius: "3px", padding: "0 3px",
          },
        }, "nunchi.channels"),
        ". The channel must also be one the hermes gateway listens to (allowed_channels) — " +
        "if the gateway never forwards messages from it, the gate never sees them."
      )
    );
  }

  // -------------------------------------------------------------------------
  // GlobalCard: global override settings
  // -------------------------------------------------------------------------
  function GlobalCard(props) {
    var globalOv = props.globalOverrides || {};
    var pendingGl = props.pendingGlobal || {};
    var resolvedModel = props.resolvedModel || null;

    var sendersVal = pendingGl.senders !== undefined
      ? (pendingGl.senders === null ? "" : (pendingGl.senders || ""))
      : (globalOv.senders || "");
    var verbosityVal = pendingGl.verbosity !== undefined
      ? (pendingGl.verbosity === null ? "" : (pendingGl.verbosity || ""))
      : (globalOv.verbosity || "");
    var modelVal = pendingGl.model !== undefined
      ? (pendingGl.model === null ? "" : (pendingGl.model || ""))
      : (globalOv.model || "");

    // Effective model display: use input value if editing, else API-resolved with source.
    var effectiveModelText = modelVal
      ? "currently: " + modelVal
      : "currently: " + resolvedModelLabel(resolvedModel);

    return h(
      SDKCard,
      { style: { marginBottom: "16px" } },
      h(SDKCardHeader, { className: "py-3 px-4" },
        h(SDKCardTitle, { className: "text-sm" }, "Global Overrides")
      ),
      h(SDKCardContent, { className: "px-4 pb-4 pt-3" },
        h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } },

          // senders
          h(FieldRow, {
            id: "nunchi-global-senders",
            label: "senders",
            helpInline: true,
            badge: makeProvBadge("senders", null, globalOv, null, pendingGl),
            help: sendersVal ? (HELP["senders_" + sendersVal] || null) : null,
            control: h(SDKSelect, {
              value: sendersVal,
              onValueChange: function (v) { props.onChange("senders", v === "" ? null : v); },
              placeholder: "(inherit)",
            },
              h(SDKSelectOption, { value: "" }, "(inherit)"),
              SENDERS_OPTIONS.map(function (o) {
                return h(SDKSelectOption, { key: o, value: o }, o);
              })
            ),
          }),

          // verbosity (receipt-log detail — labeled "receipt detail" to avoid
          // implying it changes the agent's own verbosity; config key stays "verbosity")
          h(FieldRow, {
            id: "nunchi-global-verbosity",
            label: "receipt detail",
            helpInline: true,
            badge: makeProvBadge("verbosity", null, globalOv, null, pendingGl),
            help: verbosityVal ? (HELP["verbosity_" + verbosityVal] || null) : null,
            control: h(SDKSelect, {
              value: verbosityVal,
              onValueChange: function (v) { props.onChange("verbosity", v === "" ? null : v); },
              placeholder: "(inherit)",
            },
              h(SDKSelectOption, { value: "" }, "(inherit)"),
              VERBOSITY_OPTIONS.map(function (o) {
                return h(SDKSelectOption, { key: o.value, value: o.value }, o.label);
              })
            ),
          }),

          // model — honest resolution with caveat tooltip
          h(FieldRow, {
            id: "nunchi-global-model",
            label: "model",
            labelWidth: "52px",
            badge: makeProvBadge("model", null, globalOv, null, pendingGl),
            help: h("span", { title: _MODEL_CAVEAT_TITLE, style: { cursor: "help" } },
              effectiveModelText),
            control: h(SDKInput, {
              id: "nunchi-global-model",
              type: "text",
              value: modelVal,
              onChange: function (e) { props.onChange("model", e.target.value || null); },
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
    var hasStoredOverrides = Object.keys(chOv).length > 0;
    var resolvedModel = props.resolvedModel || null;

    var _pinnedOpen = useState(false);
    var pinnedOpen = _pinnedOpen[0];
    var setPinnedOpen = _pinnedOpen[1];

    // --- allow_from: raw text local state (finding 1 + finding 1 allow_from) ---
    var allowFromArr = pendingCh.allow_from !== undefined
      ? (pendingCh.allow_from === null ? [] : (pendingCh.allow_from || []))
      : (eff.allow_from || []);
    var allowFromCanonical = Array.isArray(allowFromArr)
      ? allowFromArr.join("\n")
      : String(allowFromArr || "");

    var _rawAllowFrom = useState(allowFromCanonical);
    var rawAllowFrom = _rawAllowFrom[0];
    var setRawAllowFrom = _rawAllowFrom[1];

    var allowFromDomRef = useRef(null);
    var allowFromEditing = useRef(false);

    useEffect(function () {
      if (!allowFromEditing.current) { setRawAllowFrom(allowFromCanonical); }
    }, [allowFromCanonical]);

    useEffect(function () {
      _allowFromFlush[cid] = function () {
        if (!allowFromDomRef.current) return undefined;
        var text = allowFromDomRef.current.value;
        var lines = text.split(/[\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean);
        return lines.length > 0 ? lines : null;
      };
      return function () { delete _allowFromFlush[cid]; };
    }, [cid]);

    function _chSelectVal(key) {
      if (pendingCh[key] !== undefined) {
        return pendingCh[key] === null ? "" : (pendingCh[key] || "");
      }
      if (Object.prototype.hasOwnProperty.call(chOv, key)) { return chOv[key] || ""; }
      return "";
    }

    var sendersSelectVal = _chSelectVal("senders");
    var verbositySelectVal = _chSelectVal("verbosity");
    var enabledSelectVal;
    if (pendingCh.enabled !== undefined) {
      enabledSelectVal = pendingCh.enabled === null ? "" : String(pendingCh.enabled !== false);
    } else if (Object.prototype.hasOwnProperty.call(chOv, "enabled")) {
      enabledSelectVal = String(chOv.enabled !== false);
    } else {
      enabledSelectVal = "";
    }
    // quiet_gateway_chatter — boolean toggle, same shape as `enabled`.
    var quietChatterSelectVal;
    if (pendingCh.quiet_gateway_chatter !== undefined) {
      quietChatterSelectVal = pendingCh.quiet_gateway_chatter === null ? "" : String(pendingCh.quiet_gateway_chatter !== false);
    } else if (Object.prototype.hasOwnProperty.call(chOv, "quiet_gateway_chatter")) {
      quietChatterSelectVal = String(chOv.quiet_gateway_chatter !== false);
    } else {
      quietChatterSelectVal = "";
    }

    var sendersEff = pendingCh.senders !== undefined
      ? (pendingCh.senders === null ? (eff.senders || "all") : (pendingCh.senders || "all"))
      : (eff.senders || "all");
    var verbosityEff = pendingCh.verbosity !== undefined
      ? (pendingCh.verbosity === null ? (eff.verbosity || "normal") : (pendingCh.verbosity || "normal"))
      : (eff.verbosity || "normal");
    var modelEff = pendingCh.model !== undefined
      ? (pendingCh.model === null ? "" : (pendingCh.model || ""))
      : (eff.model || "");
    var pinnedRulesEff = pendingCh.pinned_rules !== undefined
      ? (pendingCh.pinned_rules || "")
      : (eff.pinned_rules || "");

    // Per-channel effective model: channel value takes precedence; fall back
    // to API-resolved global model with source.
    var effectiveModelText = modelEff
      ? "currently: " + modelEff
      : "currently: " + resolvedModelLabel(resolvedModel);

    function handleChange(key, value) { props.onChange(cid, key, value); }

    function handleSendersChange(v) {
      handleChange("senders", v === "" ? null : v);
      if (v !== "allowlist") { handleChange("allow_from", null); }
    }

    function handleAllowFromBlur() {
      allowFromEditing.current = false;
      var lines = rawAllowFrom.split(/[\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean);
      handleChange("allow_from", lines.length > 0 ? lines : null);
    }

    var chIdForLabel = "ch-" + cid.replace(/\W/g, "_");

    return h(
      SDKCard,
      { style: { marginBottom: "10px" } },
      h(SDKCardHeader, { className: "py-3 px-4" },
        h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
          h("div", { style: { flex: 1, minWidth: 0 } },
            displayName
              ? h("div", {
                  style: {
                    fontWeight: "600", fontSize: "13px",
                    color: "var(--color-text-primary)", marginBottom: "2px",
                  },
                }, displayName)
              : null,
            h("code", {
              style: {
                fontSize: "11px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
                fontFamily: "var(--theme-font-mono)",
                background: "color-mix(in srgb, var(--midground-base) 8%, transparent)",
                borderRadius: "3px", padding: "1px 4px",
              },
            }, cid)
          ),
          isIntroduced ? h(SDKBadge, { tone: "secondary" }, "state-introduced") : null,
          isNull ? h(SDKBadge, { tone: "destructive" }, "not gated") : null,
          hasStoredOverrides && !isNull
            ? h(SDKButton, {
                size: "sm", ghost: true, destructive: true,
                onClick: function () {
                  if (!window.confirm(
                    "Clear all overrides for channel " + (displayName || cid) + "?\n\nThis cannot be undone."
                  )) return;
                  props.onClearChannel(cid);
                },
              }, "Clear overrides")
            : null
        )
      ),
      isNull
        ? h(SDKCardContent, { className: "px-4 pb-3 pt-2" },
            h(HelpText, null, "Disabled by state or not matched by config.yaml"))
        : h(SDKCardContent, { className: "px-4 pb-4 pt-3" },
            h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } },

              h(FieldRow, {
                id: chIdForLabel + "-enabled", label: "enabled",
                badge: makeProvBadge("enabled", chOv, globalOv, pendingCh, null),
                control: h(SDKSelect, {
                  id: chIdForLabel + "-enabled",
                  value: enabledSelectVal,
                  onValueChange: function (v) {
                    handleChange("enabled", v === "" ? null : (v === "true"));
                  },
                },
                  h(SDKSelectOption, { value: "" }, "(inherit)"),
                  h(SDKSelectOption, { value: "true" }, "true"),
                  h(SDKSelectOption, { value: "false" }, "false")
                ),
              }),

              h(FieldRow, {
                id: chIdForLabel + "-quiet_gateway_chatter", label: "quiet gateway chatter",
                badge: makeProvBadge("quiet_gateway_chatter", chOv, globalOv, pendingCh, null),
                help: "When true, keeps Hermes per-turn chatter (steer/queue busy-ACKs, tool progress, compression status, the • Grant spent notice) out of this shared room. Final replies, credit warnings, and lifecycle notices still show. Takes effect live — no restart.",
                control: h(SDKSelect, {
                  id: chIdForLabel + "-quiet_gateway_chatter",
                  value: quietChatterSelectVal,
                  onValueChange: function (v) {
                    handleChange("quiet_gateway_chatter", v === "" ? null : (v === "true"));
                  },
                },
                  h(SDKSelectOption, { value: "" }, "(inherit)"),
                  h(SDKSelectOption, { value: "true" }, "true"),
                  h(SDKSelectOption, { value: "false" }, "false")
                ),
              }),

              h(FieldRow, {
                id: chIdForLabel + "-senders", label: "senders", helpInline: true,
                badge: makeProvBadge("senders", chOv, globalOv, pendingCh, null),
                help: HELP["senders_" + sendersEff] || HELP.senders_all,
                control: h(SDKSelect, {
                  id: chIdForLabel + "-senders",
                  value: sendersSelectVal,
                  onValueChange: handleSendersChange,
                },
                  h(SDKSelectOption, { value: "" }, "(inherit)"),
                  SENDERS_OPTIONS.map(function (o) {
                    return h(SDKSelectOption, { key: o, value: o }, o);
                  })
                ),
              }),

              sendersEff === "allowlist" || sendersSelectVal === "allowlist"
                ? h("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } },
                    h(SDKLabel, {
                      htmlFor: chIdForLabel + "-allow-from",
                      style: { fontSize: "12px", color: "var(--color-text-secondary)" },
                    }, "allow_from"),
                    h("textarea", {
                      id: chIdForLabel + "-allow-from",
                      ref: allowFromDomRef,
                      value: rawAllowFrom,
                      onFocus: function () { allowFromEditing.current = true; },
                      onBlur: handleAllowFromBlur,
                      onChange: function (e) { setRawAllowFrom(e.target.value); },
                      placeholder: "user_name or user_id\none per line or comma-separated",
                      rows: 3,
                      style: TEXTAREA_STYLE,
                    })
                  )
                : null,

              h(FieldRow, {
                id: chIdForLabel + "-verbosity", label: "receipt detail", helpInline: true,
                badge: makeProvBadge("verbosity", chOv, globalOv, pendingCh, null),
                help: HELP["verbosity_" + verbosityEff] || HELP.verbosity_normal,
                control: h(SDKSelect, {
                  id: chIdForLabel + "-verbosity",
                  value: verbositySelectVal,
                  onValueChange: function (v) { handleChange("verbosity", v === "" ? null : v); },
                },
                  h(SDKSelectOption, { value: "" }, "(inherit)"),
                  VERBOSITY_OPTIONS.map(function (o) {
                    return h(SDKSelectOption, { key: o.value, value: o.value }, o.label);
                  })
                ),
              }),

              // model — honest resolution with caveat tooltip
              h(FieldRow, {
                id: chIdForLabel + "-model", label: "model", labelWidth: "52px",
                badge: makeProvBadge("model", chOv, globalOv, pendingCh, null),
                help: h("span", { title: _MODEL_CAVEAT_TITLE, style: { cursor: "help" } },
                  effectiveModelText),
                control: h(SDKInput, {
                  id: chIdForLabel + "-model",
                  type: "text", value: modelEff,
                  onChange: function (e) { handleChange("model", e.target.value || null); },
                  placeholder: eff.model || "inherit",
                  style: { fontSize: "12px", height: "32px", flex: "1" },
                }),
              }),

              // pinned_rules — collapsible
              h("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } },
                h("button", {
                  type: "button",
                  onClick: function () { setPinnedOpen(!pinnedOpen); },
                  style: {
                    display: "inline-flex", alignItems: "center", gap: "6px",
                    background: "none", border: "none", cursor: "pointer", padding: "0",
                    color: "var(--color-text-secondary)", fontSize: "12px",
                    textAlign: "left", fontFamily: "var(--theme-font-sans)",
                  },
                },
                  h("span", {
                    "aria-hidden": "true",
                    style: {
                      display: "inline-block",
                      transform: pinnedOpen ? "rotate(90deg)" : "rotate(0deg)",
                      transition: "transform 0.15s ease", fontSize: "8px",
                    },
                  }, "►"),
                  "Room governance (pinned rules)",
                  makeProvBadge("pinned_rules", chOv, globalOv, pendingCh, null)
                ),
                pinnedOpen
                  ? h("div", {
                      style: { display: "flex", flexDirection: "column", gap: "4px", paddingLeft: "14px" },
                    },
                      h(HelpText, null, HELP.pinned_rules),
                      h("textarea", {
                        value: pinnedRulesEff,
                        onChange: function (e) { handleChange("pinned_rules", e.target.value || null); },
                        placeholder: "Paste governance text here…",
                        rows: 4,
                        style: Object.assign({}, TEXTAREA_STYLE, {
                          fontFamily: "var(--theme-font-sans)", marginTop: "4px",
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
  // ReceiptDetailField: labeled row for the expanded receipt detail panel.
  // -------------------------------------------------------------------------
  function ReceiptDetailField(props) {
    return h(
      "div",
      {
        style: {
          display: "grid", gridTemplateColumns: "110px 1fr",
          gap: "2px 8px", alignItems: "baseline", marginBottom: "4px",
        },
      },
      h("span", {
        style: {
          fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
          fontWeight: "600", letterSpacing: "0.05em", textTransform: "uppercase",
        },
      }, props.label),
      h("span", {
        style: Object.assign(
          { fontSize: "11px", color: "var(--color-text-secondary)", wordBreak: "break-all" },
          props.mono
            ? {
                fontFamily: "var(--theme-font-mono)", fontSize: "10px",
                background: "color-mix(in srgb, var(--midground-base) 6%, transparent)",
                borderRadius: "3px", padding: "1px 4px",
              }
            : {}
        ),
      }, props.children)
    );
  }

  // -------------------------------------------------------------------------
  // ReceiptRow: single receipt entry with collapsible detail panel.
  // Button semantics, aria-expanded, keyboard accessible (Enter/Space on
  // the button element activates the toggle).
  // -------------------------------------------------------------------------
  function ReceiptRow(props) {
    var r = props.receipt;
    var channelNames = props.channelNames || {};

    var _expanded = useState(false);
    var expanded = _expanded[0];
    var setExpanded = _expanded[1];

    var verdict = r.verdict || r.action || "?";
    var displayVerdict = (verdict === "PASS" || r.action === "skip") ? "PASS" : verdict;

    var confs = r.confidences;
    var confKeys = confs
      ? Object.keys(confs).sort(function (a, b) { return confs[b] - confs[a]; })
      : [];

    function verdictTone(v) {
      if (v === "PASS") return "destructive";
      if (v === "SPEAK") return "success";
      if (v === "ASK") return "warning";
      return "secondary";
    }

    var channelIdList = r.channel_ids || [];
    function resolveChannelName(cid) {
      return channelNames[cid] ? channelNames[cid] + " (" + cid + ")" : cid;
    }

    // Summary line (always visible inside the disclosure button).
    var summaryContent = h("div", { style: { width: "100%" } },
      h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
        // Expand/collapse chevron
        h("span", {
          "aria-hidden": "true",
          style: {
            display: "inline-block",
            transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
            transition: "transform 0.15s ease",
            fontSize: "8px", color: "var(--color-text-tertiary, var(--color-text-secondary))", flexShrink: 0,
          },
        }, "►"),
        h("span", {
          style: { color: "var(--color-text-tertiary, var(--color-text-secondary))", minWidth: "80px", flexShrink: 0 },
        }, r.ts ? formatReceiptTs(r.ts) : ""),
        h(SDKBadge, { tone: verdictTone(displayVerdict) },
          displayVerdict === "PASS" ? "PASS (suppressed)" : displayVerdict),
        r.trigger_author
          ? h("span", { style: { color: "var(--color-text-secondary)" } },
              "@" + r.trigger_author)
          : null,
        h("span", {
          style: {
            marginLeft: "auto", color: "var(--color-text-tertiary, var(--color-text-secondary))",
            fontFamily: "var(--theme-font-mono)", fontSize: "10px",
          },
        }, channelIdList.join(", "))
      ),
      // Reasons — up to 3 in collapsed view
      !expanded && r.reasons && r.reasons.length > 0
        ? h("div", {
            style: {
              marginTop: "4px", paddingLeft: "18px",
              color: "var(--color-text-secondary)", fontSize: "10px",
            },
          }, r.reasons.slice(0, 3).join(" · "))
        : null,
      // Confidence distribution — collapsed view only
      !expanded && confs && confKeys.length > 0
        ? h("div", { style: { marginTop: "6px", paddingLeft: "18px" } },
            h("div", {
              style: { display: "flex", gap: "8px", flexWrap: "wrap", fontSize: "10px", marginBottom: "4px" },
            },
              confKeys.map(function (k) {
                var isWinner = k === displayVerdict;
                return h("span", {
                  key: k,
                  style: {
                    fontWeight: isWinner ? "700" : "400",
                    color: isWinner ? "var(--color-text-primary)" : "var(--color-text-tertiary, var(--color-text-secondary))",
                  },
                }, k + " " + (confs[k] !== undefined ? Number(confs[k]).toFixed(2) : "0.00"));
              })
            ),
            h("div", {
              style: {
                height: "3px", width: "100%",
                background: "color-mix(in srgb, var(--midground-base) 10%, transparent)",
                borderRadius: "2px", overflow: "hidden",
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

    // Expanded detail panel — every field present in the receipt.
    var detailPanel = expanded
      ? h("div", {
          style: {
            marginTop: "10px", paddingTop: "10px",
            borderTop: "1px solid color-mix(in srgb, var(--midground-base) 8%, transparent)",
            paddingLeft: "18px",
          },
        },
          // Core fields (all verbosity levels)
          r.ts != null
            ? h(ReceiptDetailField, { label: "time" }, formatReceiptTsFull(r.ts)) : null,
          r.verdict
            ? h(ReceiptDetailField, { label: "verdict" }, r.verdict) : null,
          r.action
            ? h(ReceiptDetailField, { label: "action" }, r.action) : null,
          r.silent != null
            ? h(ReceiptDetailField, { label: "silent" }, String(r.silent)) : null,
          r.elapsed_ms != null
            ? h(ReceiptDetailField, { label: "elapsed" }, r.elapsed_ms + " ms") : null,
          r.message_id
            ? h(ReceiptDetailField, { label: "message_id", mono: true }, String(r.message_id))
            : null,
          channelIdList.length > 0
            ? h(ReceiptDetailField, { label: channelIdList.length > 1 ? "channels" : "channel" },
                channelIdList.map(resolveChannelName).join(", "))
            : null,

          // Normal verbosity fields
          r.trigger_author
            ? h(ReceiptDetailField, { label: "author" }, "@" + r.trigger_author) : null,
          r.trigger_author_kind
            ? h(ReceiptDetailField, { label: "author kind" }, r.trigger_author_kind) : null,
          r.history_len != null
            ? h(ReceiptDetailField, { label: "history" }, r.history_len + " messages") : null,
          r.classifier_model
            ? h(ReceiptDetailField, { label: "model", mono: true }, r.classifier_model) : null,

          // Full reasons list (un-truncated in expanded view)
          r.reasons && r.reasons.length > 0
            ? h("div", { style: { marginBottom: "6px" } },
                h("div", {
                  style: {
                    fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
                    fontWeight: "600", letterSpacing: "0.05em", textTransform: "uppercase",
                    marginBottom: "4px",
                  },
                }, "reasons (" + r.reasons.length + ")"),
                h("ul", { style: { margin: 0, paddingLeft: "14px" } },
                  r.reasons.map(function (reason, ri) {
                    return h("li", {
                      key: ri,
                      style: {
                        fontSize: "11px", color: "var(--color-text-secondary)", marginBottom: "2px",
                      },
                    }, reason);
                  })
                )
              )
            : null,

          // Full confidence table
          confs && confKeys.length > 0
            ? h("div", { style: { marginBottom: "8px" } },
                h("div", {
                  style: {
                    fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
                    fontWeight: "600", letterSpacing: "0.05em", textTransform: "uppercase",
                    marginBottom: "4px",
                  },
                }, "confidence scores"),
                h("div", { style: { display: "flex", flexDirection: "column", gap: "3px" } },
                  confKeys.map(function (k) {
                    var pct = Math.round((confs[k] || 0) * 100);
                    var isWinner = k === displayVerdict;
                    return h("div", {
                      key: k,
                      style: { display: "flex", alignItems: "center", gap: "6px", fontSize: "11px" },
                    },
                      h("span", {
                        style: {
                          width: "44px", fontWeight: isWinner ? "700" : "400",
                          color: isWinner ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                        },
                      }, k),
                      h("span", {
                        style: {
                          width: "40px", textAlign: "right",
                          color: "var(--color-text-secondary)",
                          fontFamily: "var(--theme-font-mono)", fontSize: "10px",
                        },
                      }, Number(confs[k]).toFixed(3)),
                      h("div", {
                        style: {
                          flex: 1, height: "4px",
                          background: "color-mix(in srgb, var(--midground-base) 10%, transparent)",
                          borderRadius: "2px", overflow: "hidden",
                        },
                      },
                        h("div", {
                          style: {
                            height: "100%", width: pct + "%",
                            background: k === "SPEAK" ? "var(--color-success)"
                              : k === "PASS" ? "var(--color-destructive)"
                              : k === "ASK" ? "var(--color-warning)"
                              : "var(--color-text-secondary)",
                          },
                        })
                      )
                    );
                  })
                )
              )
            : null,

          // Debug verbosity: gate payload
          r.payload
            ? h("div", { style: { marginTop: "8px" } },
                h("div", {
                  style: {
                    fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
                    fontWeight: "600", letterSpacing: "0.05em", textTransform: "uppercase",
                    marginBottom: "6px",
                  },
                }, "gate payload"),
                // Trigger content
                r.payload.trigger && r.payload.trigger.content != null
                  ? h("div", { style: { marginBottom: "6px" } },
                      h("div", {
                        style: { fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))", marginBottom: "2px" },
                      }, "trigger content"),
                      h("pre", {
                        style: {
                          fontFamily: "var(--theme-font-mono)", fontSize: "10px",
                          color: "var(--color-text-secondary)",
                          background: "color-mix(in srgb, var(--midground-base) 6%, transparent)",
                          borderRadius: "3px", padding: "6px 8px", margin: 0,
                          whiteSpace: "pre-wrap", wordBreak: "break-word",
                          maxHeight: "120px", overflowY: "auto",
                        },
                      }, String(r.payload.trigger.content))
                    )
                  : null,
                // History entries
                r.payload.history && r.payload.history.length > 0
                  ? h("div", { style: { marginBottom: "6px" } },
                      h("div", {
                        style: { fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))", marginBottom: "2px" },
                      }, "history (" + r.payload.history.length + " entries)"),
                      h("div", {
                        style: {
                          maxHeight: "100px", overflowY: "auto",
                          display: "flex", flexDirection: "column", gap: "2px",
                        },
                      },
                        r.payload.history.map(function (entry, hi) {
                          return h("div", {
                            key: hi,
                            style: {
                              fontSize: "10px", color: "var(--color-text-secondary)",
                              fontFamily: "var(--theme-font-mono)",
                            },
                          }, "[" + (entry.author || "?") + " / " + (entry.author_kind || "?") + "] " +
                            (entry.content ? entry.content.slice(0, 80) : ""));
                        })
                      )
                    )
                  : null,
                // Pinned rules presence
                r.payload.pinned_rules
                  ? h(ReceiptDetailField, { label: "pinned rules" },
                      "present (" + String(r.payload.pinned_rules).length + " chars)")
                  : null
              )
            : null,

          // Debug verbosity: directive
          r.directive
            ? h("div", { style: { marginTop: "8px" } },
                h("div", {
                  style: {
                    fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
                    fontWeight: "600", letterSpacing: "0.05em", textTransform: "uppercase",
                    marginBottom: "6px",
                  },
                }, "directive"),
                Object.keys(r.directive).map(function (k) {
                  var v = r.directive[k];
                  var display = typeof v === "object" && v !== null
                    ? JSON.stringify(v)
                    : String(v);
                  return h(ReceiptDetailField, { key: k, label: k, mono: true }, display);
                })
              )
            : null,

          // Muted note when debug fields absent
          !r.payload && !r.directive
            ? h("p", {
                style: {
                  fontSize: "10px", color: "var(--color-text-tertiary, var(--color-text-secondary))",
                  fontStyle: "italic", margin: "6px 0 0 0",
                },
              }, "Message content is only recorded at debug verbosity.")
            : null
        )
      : null;

    return h(
      "div",
      {
        style: {
          borderRadius: "var(--theme-radius, 4px)",
          background: "color-mix(in srgb, var(--midground-base) 4%, transparent)",
          border: "1px solid color-mix(in srgb, var(--midground-base) 8%, transparent)",
          overflow: "hidden",
          // Keep full height inside the flex-column scroll container; without
          // this, many receipts get squished to fit maxHeight (unreadable
          // slivers) and the container never overflows, so it can't scroll.
          flexShrink: 0,
        },
      },
      // Disclosure button — full width, left-aligned, button semantics.
      h("button", {
        type: "button",
        "aria-expanded": expanded,
        onClick: function () { setExpanded(!expanded); },
        style: {
          display: "block", width: "100%", textAlign: "left",
          background: "none", border: "none", cursor: "pointer",
          padding: "8px 10px", fontSize: "11px",
          color: "var(--color-text-primary)",
          fontFamily: "var(--theme-font-sans)",
        },
      }, summaryContent),
      // Detail panel — only rendered when expanded.
      detailPanel
        ? h("div", { style: { padding: "0 10px 10px 10px" } }, detailPanel)
        : null
    );
  }

  // -------------------------------------------------------------------------
  // ReceiptsPanel: polls GET /receipts with polling controls
  // -------------------------------------------------------------------------
  function ReceiptsPanel(props) {
    var channelNames = props.channelNames || {};

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

    useEffect(function () {
      try {
        localStorage.setItem(LS_POLL_KEY, JSON.stringify({ paused: paused, interval: pollInterval }));
      } catch (_) {}
    }, [paused, pollInterval]);

    useEffect(function () {
      function onVis() { setIsHidden(document.hidden); }
      document.addEventListener("visibilitychange", onVis);
      return function () { document.removeEventListener("visibilitychange", onVis); };
    }, []);

    var poll = useCallback(function () {
      fetchJSON(API_BASE + "/receipts?limit=50")
        .then(function (data) { setReceipts(data.receipts || []); setErr(null); })
        .catch(function (e) { setErr(String(e)); });
    }, []);

    useEffect(function () {
      if (paused || isHidden || pollInterval === 0) return;
      poll();
      var id = setInterval(poll, pollInterval);
      return function () { clearInterval(id); };
    }, [poll, paused, isHidden, pollInterval]);

    var currentIntervalLabel = (POLL_INTERVALS.find(function (pi) {
      return pi.value === pollInterval;
    }) || { label: "?" }).label;

    return h(SDKCard, null,
      h(SDKCardHeader, { className: "py-3 px-4" },
        h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
          h(SDKCardTitle, { className: "text-sm", style: { flex: "1" } }, "Gate Receipts (newest first)"),
          h(SDKSelect, {
            value: String(pollInterval),
            onValueChange: function (v) { setPollInterval(parseInt(v, 10)); },
          },
            POLL_INTERVALS.map(function (pi) {
              return h(SDKSelectOption, { key: pi.value, value: String(pi.value) }, pi.label);
            })
          ),
          h(SDKButton, {
            size: "sm", ghost: true, outlined: paused,
            onClick: function () { setPaused(!paused); },
            title: paused ? "Resume polling" : "Pause polling",
          }, paused ? "► Resume" : "⏸ Pause"),
          isHidden
            ? h(SDKBadge, { tone: "secondary" }, "suspended")
            : (paused
                ? h(SDKBadge, { tone: "warning" }, "paused")
                : (pollInterval === 0
                    ? h(SDKBadge, { tone: "secondary" }, "off")
                    : h(SDKBadge, { tone: "secondary" }, "polling " + currentIntervalLabel)))
        )
      ),
      h(SDKCardContent, { className: "px-4 pb-4 pt-2" },
        // Verdict legend
        h("div", {
          style: {
            display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center",
            paddingBottom: "10px", marginBottom: "10px",
            borderBottom: "1px solid color-mix(in srgb, var(--midground-base) 10%, transparent)",
          },
        },
          h(SDKBadge, { tone: "destructive" }, "PASS (suppressed)"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } }, "= no message"),
          h("span", { style: { color: "var(--color-text-tertiary, var(--color-text-secondary))" } }, "·"),
          h(SDKBadge, { tone: "secondary" }, "ACK"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } }, "= brief presence signal"),
          h("span", { style: { color: "var(--color-text-tertiary, var(--color-text-secondary))" } }, "·"),
          h(SDKBadge, { tone: "warning" }, "ASK"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } }, "= one clarifying question"),
          h("span", { style: { color: "var(--color-text-tertiary, var(--color-text-secondary))" } }, "·"),
          h(SDKBadge, { tone: "success" }, "SPEAK"),
          h("span", { style: { fontSize: "11px", color: "var(--color-text-secondary)" } }, "= full turn")
        ),
        // Receipt rows — now expandable
        err
          ? h("p", { style: { color: "var(--color-destructive)", fontSize: "12px", margin: 0 } }, err)
          : receipts.length === 0
          ? h("p", { style: { color: "var(--color-text-tertiary, var(--color-text-secondary))", fontSize: "12px", margin: 0 } },
              "No receipts yet.")
          : h("div", {
              style: {
                maxHeight: "600px", overflowY: "auto",
                display: "flex", flexDirection: "column", gap: "6px",
              },
            },
              receipts.map(function (r, i) {
                return h(ReceiptRow, { key: i, receipt: r, channelNames: channelNames });
              })
            )
      )
    );
  }

  // -------------------------------------------------------------------------
  // SettingsContent — hoisted to module scope (finding 1).
  // -------------------------------------------------------------------------
  function SettingsContent(props) {
    var stateData = props.stateData || {};
    var effective = props.effective || {};
    var globalOv = props.globalOv || {};
    var chStates = props.chStates || {};
    var channelNames = props.channelNames || {};
    var pendingGlobal = props.pendingGlobal || {};
    var pendingChannels = props.pendingChannels || {};
    var allCids = props.allCids || [];
    var baselineChannels = props.baselineChannels || {};
    var handleChannelChange = props.handleChannelChange;
    var handleGlobalChange = props.handleGlobalChange;
    var handleClearChannel = props.handleClearChannel;
    var handleAddChannel = props.handleAddChannel;
    var availableChannels = props.availableChannels || [];
    var resolvedModel = props.resolvedModel || null;

    return h("div", null,
      h("p", {
        style: {
          fontSize: "12px", color: "var(--color-text-secondary)",
          margin: "0 0 16px 0", lineHeight: "1.55",
        },
      },
        "nunchi is an admission gate: before an agent replies in a channel, the gate " +
        "judges whether it's the agent's turn to speak. These settings tune that " +
        "judgment per channel."
      ),
      h(GlobalCard, {
        globalOverrides: globalOv,
        pendingGlobal: pendingGlobal,
        resolvedModel: resolvedModel,
        onChange: handleGlobalChange,
      }),
      h(SectionDivider, { label: "Channels" }),
      allCids.length === 0
        ? h("p", { style: { fontSize: "12px", color: "var(--color-text-tertiary, var(--color-text-secondary))", margin: 0 } },
            "No channels configured.")
        : allCids.map(function (cid) {
            var eff = effective[cid] !== undefined ? effective[cid] : null;
            var displayEff = eff;
            if (eff && pendingChannels[cid]) {
              displayEff = Object.assign({}, eff, pendingChannels[cid]);
            }
            return h(ChannelCard, {
              key: cid, cid: cid,
              displayName: channelNames[cid] || null,
              effective: displayEff,
              chOverrides: chStates[cid] || {},
              globalOverrides: globalOv,
              pendingCh: pendingChannels[cid] || {},
              isIntroduced: !baselineChannels[cid],
              baseline: stateData.baseline || {},
              resolvedModel: resolvedModel,
              onChange: handleChannelChange,
              onClearChannel: handleClearChannel,
            });
          }),
      h(AddChannelControl, {
        availableChannels: availableChannels,
        onAdd: handleAddChannel,
      })
    );
  }

  // -------------------------------------------------------------------------
  // Main plugin component
  // -------------------------------------------------------------------------
  function NunchiPanel() {
    var _stateData = useState({
      baseline: {}, overrides: {}, effective: {}, channel_names: {},
      available_channels: [], resolved_model: { value: null, source: null },
    });
    var stateData = _stateData[0], setStateData = _stateData[1];
    var _pending = useState({});
    var pending = _pending[0], setPending = _pending[1];
    var _status = useState(null);
    var status = _status[0], setStatus = _status[1];
    var _loading = useState(true);
    var loading = _loading[0], setLoading = _loading[1];
    var _apiVersion = useState(null);
    var apiVersion = _apiVersion[0], setApiVersion = _apiVersion[1];
    var _hasLoaded = useState(false);
    var hasLoaded = _hasLoaded[0], setHasLoaded = _hasLoaded[1];

    var load = useCallback(function () {
      setLoading(true);
      return fetchJSON(API_BASE + "/state")
        .then(function (data) {
          setStateData(data);
          setApiVersion(data.api_version || null);
          setHasLoaded(true);
          setLoading(false);
        })
        .catch(function (e) {
          setStatus("Error loading state: " + e);
          setLoading(false);
        });
    }, []);

    useEffect(function () { load(); }, [load]);

    var handleChannelChange = useCallback(function (cid, key, value) {
      setPending(function (prev) {
        var channels = Object.assign({}, prev.channels || {});
        var ch = Object.assign({}, channels[cid] || {});
        var baseline = stateData.baseline || {};
        var baselineChs = baseline.channels || baseline.channel_ids;
        var chCfg = {};
        if (baselineChs && typeof baselineChs === "object" && !Array.isArray(baselineChs)) {
          chCfg = baselineChs[cid] || {};
        }
        var baselineVal = key in chCfg ? chCfg[key] : baseline[key];
        var coerced = (key === "enabled" || key === "quiet_gateway_chatter") ? value === "true" : value;
        if (Array.isArray(coerced)) {
          ch[key] = coerced;
        } else {
          if (coerced === "" && (key === "model" || key === "pinned_rules")) { coerced = null; }
          ch[key] = coerced === baselineVal ? null : coerced;
        }
        channels[cid] = ch;
        return Object.assign({}, prev, { channels: channels });
      });
    }, [stateData]);

    var handleGlobalChange = useCallback(function (key, value) {
      setPending(function (prev) {
        var g = Object.assign({}, prev.global || {});
        g[key] = (value === "" || value === undefined) ? null : value;
        return Object.assign({}, prev, { global: g });
      });
    }, []);

    // Add-channel handler: stage channels.{cid}.enabled=true as a pending change.
    var handleAddChannel = useCallback(function (cid) {
      // Pass "true" (string) so handleChannelChange's coerce line (value === "true")
      // produces boolean true and stages enabled: true in the pending state.
      handleChannelChange(cid, "enabled", "true");
    }, [handleChannelChange]);

    function setSuccessStatus(msg) {
      setStatus(msg);
      setTimeout(function () {
        setStatus(function (prev) { return prev === msg ? null : prev; });
      }, SUCCESS_DISMISS_MS);
    }

    var save = useCallback(function () {
      var patchToSend = pending;
      var flushed = {};
      Object.keys(_allowFromFlush).forEach(function (cid) {
        var parsed = _allowFromFlush[cid]();
        if (parsed !== undefined) { flushed[cid] = parsed; }
      });
      if (Object.keys(flushed).length > 0) {
        var mergedChannels = Object.assign({}, pending.channels || {});
        Object.keys(flushed).forEach(function (cid) {
          var existing = Object.assign({}, mergedChannels[cid] || {});
          existing.allow_from = flushed[cid];
          mergedChannels[cid] = existing;
        });
        patchToSend = Object.assign({}, pending, { channels: mergedChannels });
      }
      fetchJSON(API_BASE + "/state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patchToSend),
      })
        .then(function (resp) {
          var rejectedKeys = (resp && resp.rejected_keys) || [];
          if (rejectedKeys.length > 0) {
            setStatus(
              "Server did not accept: " + rejectedKeys.join(", ") +
              " — the dashboard service may be running an older plugin version"
            );
          } else {
            setSuccessStatus("Saved.");
          }
          setPending({});
          load();
        })
        .catch(function (e) { setStatus("Save failed: " + e); });
    }, [pending, load]);

    var handleClearChannel = useCallback(function (cid) {
      var channelPatch = {};
      channelPatch[cid] = {};
      fetchJSON(API_BASE + "/state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channels: channelPatch }),
      })
        .then(function (resp) {
          var rejectedKeys = (resp && resp.rejected_keys) || [];
          if (rejectedKeys.length > 0) {
            setStatus("Clear failed: server did not accept some keys");
          } else {
            setSuccessStatus("Overrides cleared for channel.");
          }
          setPending(function (prev) {
            var channels = Object.assign({}, prev.channels || {});
            delete channels[cid];
            return Object.assign({}, prev, { channels: channels });
          });
          load();
        })
        .catch(function (e) { setStatus("Clear failed: " + e); });
    }, [load]);

    var resetAll = useCallback(function () {
      if (!window.confirm("Clear all nunchi-gate runtime overrides?")) return;
      fetchJSON(API_BASE + "/state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ global: {}, channels: {} }),
      })
        .then(function (resp) {
          var rejectedKeys = (resp && resp.rejected_keys) || [];
          setPending({});
          if (rejectedKeys.length > 0) {
            setStatus("Reset failed: server did not accept some keys");
            load();
          } else {
            Promise.resolve(load()).then(function () {
              setSuccessStatus("All overrides cleared.");
            });
          }
        })
        .catch(function (e) { setStatus("Reset failed: " + e); });
    }, [load]);

    var effective = stateData.effective || {};
    var overrides = stateData.overrides || {};
    var globalOv = overrides.global || {};
    var chStates = overrides.channels || {};
    var channelNames = stateData.channel_names || {};
    var availableChannels = stateData.available_channels || [];
    var resolvedModel = stateData.resolved_model || null;

    var pendingGlobal = pending.global || {};
    var pendingChannels = pending.channels || {};
    var allCids = Array.from(
      new Set(Object.keys(effective).concat(Object.keys(pendingChannels)))
    ).sort();

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

    var hasPendingGlobal = Object.keys(pendingGlobal).some(function (k) {
      return pendingGlobal[k] !== undefined;
    });
    var hasPendingChannels = Object.keys(pendingChannels).some(function (cid) {
      return Object.keys(pendingChannels[cid] || {}).length > 0;
    });
    var hasPending = hasPendingGlobal || hasPendingChannels;

    var isError = status && (
      status.indexOf("failed") !== -1 ||
      status.indexOf("Error") !== -1 ||
      status.indexOf("did not accept") !== -1
    );

    var showVersionBanner = hasLoaded && !loading &&
      (!apiVersion || parseInt(apiVersion, 10) < parseInt(EXPECTED_API_VERSION, 10));

    return h("div", {
      style: {
        padding: "1rem 1.5rem", maxWidth: "56rem",
        fontFamily: "var(--theme-font-sans)", color: "var(--color-text-primary)",
      },
    },
      showVersionBanner
        ? h("div", {
            style: {
              background: "color-mix(in srgb, var(--color-warning) 15%, transparent)",
              border: "1px solid color-mix(in srgb, var(--color-warning) 60%, transparent)",
              borderRadius: "var(--theme-radius, 4px)",
              padding: "10px 14px", fontSize: "12px",
              color: "var(--color-text-primary)", marginBottom: "16px", lineHeight: "1.55",
            },
          },
          "⚠️ The dashboard service is running an outdated nunchi backend — " +
          "restart the hermes dashboard service to activate current features."
        )
        : null,

      h("div", {
        style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" },
      },
        h("h2", {
          style: {
            fontSize: "14px", fontWeight: "700", margin: 0,
            color: "var(--midground)", letterSpacing: "0.1em", textTransform: "uppercase",
          },
        }, "Nunchi Gate"),
        loading
          ? h("span", { style: { fontSize: "12px", color: "var(--color-text-tertiary, var(--color-text-secondary))" } }, "Loading…")
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

      h("div", {
        style: { display: "flex", gap: "8px", alignItems: "center", marginBottom: "20px", flexWrap: "wrap" },
      },
        h(SDKButton, {
          size: "sm", disabled: !hasPending,
          title: hasPending ? undefined : "No unsaved changes",
          onClick: save,
        }, "Save"),
        hasPending
          ? h("span", { style: { fontSize: "12px", color: "var(--color-warning)", fontWeight: "600" } },
              "Unsaved changes")
          : null,
        h(SDKButton, { size: "sm", ghost: true, onClick: load }, "Refresh"),
        h(SDKButton, { size: "sm", ghost: true, destructive: true, onClick: resetAll },
          "Reset All Overrides")
      ),

      h(SDKTabs, { defaultValue: "settings" },
        function (activeTab, setActiveTab) {
          return h("div", { style: { display: "flex", flexDirection: "column", gap: "16px" } },
            h(SDKTabsList, null,
              h(SDKTabsTrigger, {
                value: "settings", active: activeTab === "settings",
                onClick: function () { setActiveTab("settings"); },
              }, "Settings"),
              h(SDKTabsTrigger, {
                value: "receipts", active: activeTab === "receipts",
                onClick: function () { setActiveTab("receipts"); },
              }, "Receipts")
            ),
            activeTab === "settings"
              ? h(SettingsContent, {
                  stateData: stateData,
                  effective: effective, globalOv: globalOv, chStates: chStates,
                  channelNames: channelNames, pendingGlobal: pendingGlobal,
                  pendingChannels: pendingChannels, allCids: allCids,
                  baselineChannels: baselineChannels,
                  availableChannels: availableChannels,
                  resolvedModel: resolvedModel,
                  handleChannelChange: handleChannelChange,
                  handleGlobalChange: handleGlobalChange,
                  handleClearChannel: handleClearChannel,
                  handleAddChannel: handleAddChannel,
                })
              : h(ReceiptsPanel, { channelNames: channelNames })
          );
        }
      )
    );
  }

  window.__NUNCHI_REGISTERED__ = true;
  PLUGINS.register("nunchi", NunchiPanel);
})();
