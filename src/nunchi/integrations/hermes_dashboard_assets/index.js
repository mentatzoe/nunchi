/**
 * Nunchi V2 dashboard.
 *
 * Runs inside Hermes's authenticated dashboard host. No build step and no
 * Hermes source changes are required.
 */
(function () {
  "use strict";

  if (window.__NUNCHI_REGISTERED__) return;
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var PLUGINS = window.__HERMES_PLUGINS__;
  if (!SDK || !PLUGINS) {
    setTimeout(function () {
      var script = document.createElement("script");
      script.src = "/dashboard-plugins/nunchi/index.js";
      document.head.appendChild(script);
    }, 500);
    return;
  }

  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useCallback = SDK.hooks.useCallback;
  var fetchJSON = SDK.fetchJSON;
  var C = SDK.components || {};
  var Button = C.Button || "button";
  var Input = C.Input || "input";
  var Label = C.Label || "label";
  var Card = C.Card || "section";
  var CardHeader = C.CardHeader || "header";
  var CardTitle = C.CardTitle || "h3";
  var CardContent = C.CardContent || "div";
  var API = "/api/plugins/nunchi";
  var DEFAULT_ATTENTION_PROVIDER = "nous";
  var DEFAULT_ATTENTION_MODEL = "deepseek/deepseek-v4-flash";
  var SUPPORTED_PLATFORMS = ["discord", "telegram"];

  var styles = {
    page: { display: "flex", flexDirection: "column", gap: "16px" },
    row: { display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "end" },
    field: { display: "flex", flexDirection: "column", gap: "5px", flex: "1 1 220px" },
    hint: { fontSize: "12px", color: "var(--color-text-secondary)", lineHeight: "1.45" },
    status: {
      padding: "10px 12px",
      border: "1px solid color-mix(in srgb, var(--midground-base) 18%, transparent)",
      borderRadius: "var(--theme-radius, 6px)",
      fontSize: "12px",
      lineHeight: "1.5"
    },
    textarea: {
      width: "100%",
      boxSizing: "border-box",
      background: "transparent",
      border: "1px solid color-mix(in srgb, var(--midground-base) 20%, transparent)",
      borderRadius: "var(--theme-radius, 6px)",
      color: "var(--color-text-primary)",
      fontFamily: "var(--theme-font-mono, monospace)",
      fontSize: "12px",
      lineHeight: "1.5",
      padding: "9px",
      resize: "vertical"
    },
    receipt: {
      padding: "9px 0",
      borderBottom: "1px solid color-mix(in srgb, var(--midground-base) 12%, transparent)",
      fontSize: "12px"
    }
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function field(label, value, onChange, options) {
    options = options || {};
    return h("div", { style: styles.field },
      h(Label, null, label),
      options.multiline
        ? h("textarea", {
            value: value == null ? "" : String(value),
            rows: options.rows || 3,
            style: styles.textarea,
            onChange: function (event) { onChange(event.target.value); }
          })
        : h(Input, {
            value: value == null ? "" : String(value),
            type: options.type || "text",
            onChange: function (event) { onChange(event.target.value); }
          }),
      options.help ? h("span", { style: styles.hint }, options.help) : null
    );
  }

  function selectField(label, value, onChange, choices) {
    return h("div", { style: styles.field },
      h(Label, null, label),
      h("select", {
        value: value,
        onChange: function (event) { onChange(event.target.value); },
        style: Object.assign({}, styles.textarea, { padding: "7px", resize: "none" })
      }, choices.map(function (choice) {
        return h("option", { key: choice.value, value: choice.value }, choice.label);
      }))
    );
  }

  function setPath(document, path, value) {
    var next = clone(document);
    var cursor = next;
    for (var index = 0; index < path.length - 1; index += 1) {
      cursor = cursor[path[index]];
    }
    cursor[path[path.length - 1]] = value;
    return next;
  }

  function defaultRoom(document, channels) {
    var suffix = String(Date.now());
    var supportedChannels = (channels || []).filter(function (item) {
      return SUPPORTED_PLATFORMS.indexOf(item.platform) !== -1;
    });
    var platform = supportedChannels.length
      ? supportedChannels[0].platform
      : "discord";
    var roomId = supportedChannels.length ? supportedChannels[0].id : "";
    return {
      binding: {
        participant_id: "agent",
        actor_id: "",
        platform: platform,
        room_id: roomId,
        continuity_scope_id: roomId
          ? platform + "-room-" + roomId
          : "room-" + suffix,
        names: ["Agent"],
        room_kind: "group",
        provenance: "operator:hermes-dashboard"
      },
      profile: {
        document: {
          profile_id: "profile-" + suffix,
          participant_id: "agent",
          actor_id: "",
          instructions: "Judge whether this participant should take the turn.",
          provenance: "operator:hermes-dashboard"
        }
      },
      attention: {
        model: {
          provider: DEFAULT_ATTENTION_PROVIDER,
          model: DEFAULT_ATTENTION_MODEL
        },
        policy: {
          suppression_enabled: true,
          suppression_recovery_verified: false
        }
      },
      limits: {},
      participant: { timeout_seconds: 300, max_expansions: 3 }
    };
  }

  function RoomEditor(props) {
    var room = props.room;
    var index = props.index;
    var doc = props.document;
    var binding = room.binding || {};
    var profile = room.profile || {};
    var inline = profile.document || null;
    var attentionModel = (room.attention || {}).model || {};
    var policy = (room.attention || {}).policy || {};
    var base = ["rooms", index];
    var platforms = SUPPORTED_PLATFORMS.map(function (platform) {
      return {
        value: platform,
        label: platform.charAt(0).toUpperCase() + platform.slice(1)
      };
    });
    var channels = [{ value: "", label: "Choose a discovered room" }].concat(
      (props.channels || []).filter(function (item) {
        return item.platform === binding.platform;
      }).map(function (item) {
        var name = item.guild ? item.guild + " / " + item.name : item.name;
        return { value: item.id, label: name + " (" + item.id + ")" };
      })
    );

    function update(path, value) {
      props.onDocument(setPath(doc, base.concat(path), value));
    }

    function updateExactIdentity(name, value) {
      var next = setPath(doc, base.concat(["binding", name]), value);
      if (inline) {
        next = setPath(next, base.concat(["profile", "document", name]), value);
      }
      props.onDocument(next);
    }

    function updatePlatform(value) {
      var previous = binding.platform || "";
      var next = setPath(doc, base.concat(["binding", "platform"]), value);
      if (previous && previous !== value) {
        next = setPath(next, base.concat(["binding", "actor_id"]), "");
        next = setPath(next, base.concat(["binding", "room_id"]), "");
        next = setPath(next, base.concat(["binding", "continuity_scope_id"]), "");
        next = setPath(next, base.concat(["binding", "room_name"]), "");
        if (inline) {
          next = setPath(
            next,
            base.concat(["profile", "document", "actor_id"]),
            ""
          );
        }
      }
      props.onDocument(next);
    }

    function policyValue(name, fallback) {
      return policy[name] === undefined ? fallback : policy[name];
    }

    return h(Card, null,
      h(CardHeader, null,
        h("div", { style: Object.assign({}, styles.row, { alignItems: "center" }) },
          h(CardTitle, { style: { flex: "1 1 auto" } },
            (binding.platform || "room") + " · " + (binding.room_id || "not selected")
          ),
          h(Button, {
            size: "sm",
            destructive: true,
            onClick: function () { props.onRemove(index); }
          }, "Remove")
        )
      ),
      h(CardContent, null,
        h("div", { style: styles.row },
          selectField("Platform", binding.platform || "discord", function (value) {
            updatePlatform(value);
          }, platforms),
          selectField("Discovered room", binding.room_id || "", function (value) {
            update(["binding", "room_id"], value);
          }, channels),
          field("Room ID", binding.room_id, function (value) {
            update(["binding", "room_id"], value);
          }, { help: "Manual IDs are supported when Hermes has not discovered the room." })
        ),
        h("div", { style: styles.row },
          field("Participant ID", binding.participant_id, function (value) {
            updateExactIdentity("participant_id", value);
          }),
          field("Actor ID", binding.actor_id, function (value) {
            updateExactIdentity("actor_id", value);
          }, {
            help: "Required exact bot identity, for example discord:actor:<bot user ID> or telegram:actor:<bot user ID>."
          }),
          field("Continuity scope", binding.continuity_scope_id, function (value) {
            update(["binding", "continuity_scope_id"], value);
          })
        ),
        h("div", { style: styles.row },
          field("Names", (binding.names || []).join(", "), function (value) {
            update(["binding", "names"], value.split(",").map(function (item) {
              return item.trim();
            }).filter(Boolean));
          }, { help: "Comma-separated names used for exact mention evidence." }),
          field("Gate deadline (seconds)",
            (room.participant || {}).timeout_seconds,
            function (value) {
              update(["participant", "timeout_seconds"], Number(value));
            }, {
              type: "number",
              help: "Total deadline for observation, attention, the admitted Hermes turn, and final settlement."
            })
        ),
        inline
          ? h("div", null,
              h("div", { style: styles.row },
                field("Profile ID", inline.profile_id, function (value) {
                  update(["profile", "document", "profile_id"], value);
                }),
                field("Profile provenance", inline.provenance, function (value) {
                  update(["profile", "document", "provenance"], value);
                })
              ),
              field("Attention identity context", inline.instructions, function (value) {
                update(["profile", "document", "instructions"], value);
              }, {
                multiline: true,
                rows: 4,
                help: "Used only to judge whether this participant should act. Hermes's normal prompt and model remain unchanged."
              })
            )
          : h("div", { style: styles.status },
              "This room uses an external pinned participant profile. Edit it in Advanced JSON."
            ),
        h("div", { style: Object.assign({}, styles.row, { marginTop: "12px" }) },
          field("Attention provider", attentionModel.provider || "",
            function (value) {
              update(["attention", "model", "provider"], value);
            }, {
              help: "Hermes provider used only for the lower-cost attention decision."
            }),
          field("Attention model", attentionModel.model || "",
            function (value) {
              update(["attention", "model", "model"], value);
            }, {
              help: "Required. This is separate from the participant's main model. The default is the benchmarked low-cost attention model."
            })
        ),
        h("div", { style: styles.status },
          "Hermes must allow this exact provider and model under " +
          "plugins.entries.nunchi.llm. The plugin cannot grant itself that permission."
        ),
        h("div", { style: Object.assign({}, styles.row, { marginTop: "12px" }) },
          h("label", { style: styles.hint },
            h("input", {
              type: "checkbox",
              checked: Boolean(policyValue("preattention_enabled", true)),
              onChange: function (event) {
                update(["attention", "policy", "preattention_enabled"], event.target.checked);
              }
            }),
            " Enable participant pre-attention"
          ),
          h("label", { style: styles.hint },
            h("input", {
              type: "checkbox",
              checked: Boolean(policyValue("suppression_enabled", true)),
              onChange: function (event) {
                update(["attention", "policy", "suppression_enabled"], event.target.checked);
              }
            }),
            " Allow social suppression"
          ),
          h("label", { style: styles.hint },
            h("input", {
              type: "checkbox",
              checked: Boolean(policyValue("suppression_recovery_verified", true)),
              onChange: function (event) {
                update(["attention", "policy", "suppression_recovery_verified"],
                  event.target.checked);
              }
            }),
            " Live suppression recovery verified"
          )
        ),
        h("div", { style: styles.row },
          selectField("Attention error action", policyValue("error_action", "WAKE"),
            function (value) {
              update(["attention", "policy", "error_action"], value);
            }, [
              { value: "WAKE", label: "Wake the participant" },
              { value: "NO_WAKE", label: "Do not wake" }
            ]),
          field("Attention timeout (seconds)", policyValue("timeout_seconds", 30),
            function (value) {
              update(["attention", "policy", "timeout_seconds"], Number(value));
            }, {
              type: "number",
              help: "An attention error remains an operational result, never a social judgment."
            })
        )
      )
    );
  }

  function ConfigPanel(props) {
    var snapshot = props.snapshot;
    var document = props.document;
    var discord = snapshot.discord_runtime || {};
    var [advanced, setAdvanced] = useState(false);
    var [raw, setRaw] = useState(JSON.stringify(document, null, 2));
    var [rawError, setRawError] = useState(null);

    useEffect(function () {
      setRaw(JSON.stringify(document, null, 2));
    }, [document]);

    function applyRaw(value) {
      setRaw(value);
      try {
        var parsed = JSON.parse(value);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          throw new Error("Configuration must be a JSON object.");
        }
        setRawError(null);
        props.onDocument(parsed);
      } catch (error) {
        setRawError(String(error.message || error));
      }
    }

    function removeRoom(index) {
      var next = clone(document);
      next.rooms.splice(index, 1);
      props.onDocument(next);
    }

    return h("div", { style: styles.page },
      h(Card, null,
        h(CardHeader, null, h(CardTitle, null, "Discord room behavior")),
        h(CardContent, null,
          discord.configuration_loadable &&
          (discord.configured_room_ids || []).length
            ? h("div", { style: styles.page },
                h("div", null,
                  "After Hermes restarts, Nunchi will listen without mentions, " +
                  "admit bot messages, and recover messages missed during restart " +
                  "only in these configured rooms. It will also prevent automatic " +
                  "thread moves there: " +
                  discord.configured_room_ids.join(", ") + "."
                ),
                h("div", { style: styles.hint },
                  "This is supplied by Nunchi's checked runtime shim. No " +
                  "DISCORD_ALLOW_BOTS, DISCORD_FREE_RESPONSE_CHANNELS, or " +
                  "DISCORD_NO_THREAD_CHANNELS setting is required, and Hermes's " +
                  "missed-message recovery does not need separate setup."
                ),
                discord.profile_wide_fallback_active
                  ? h("div", { style: styles.status },
                      "Hermes's profile-wide bot fallback is currently " +
                      discord.profile_wide_hermes_allow_bots +
                      ". Nunchi does not need it; Hermes may still admit bot " +
                      "messages outside Nunchi rooms under its normal rules."
                    )
                  : h("div", { style: styles.hint },
                      "Hermes's profile-wide bot fallback is off."
                    )
              )
            : h("div", { style: styles.hint },
                snapshot.bootstrap_required || !snapshot.configuration_valid
                  ? "No loadable Discord room configuration is saved. Complete or repair setup, then restart Hermes."
                  : "Add a Discord room, save, and restart Hermes to enable natural room conversation."
              )
        )
      ),
      h("div", { style: styles.status },
        h("strong", null,
          snapshot.bootstrap_required
            ? "First-time setup"
            : (snapshot.dashboard_writable
                ? "Editable pinned config"
                : "Read-only pinned config")
        ),
        h("div", null, snapshot.path),
        snapshot.sha256
          ? h("div", null, "SHA-256: " + snapshot.sha256)
          : h("div", null, snapshot.setup_message),
        snapshot.bootstrap_required
          ? h("div", null,
              snapshot.bootstrap_recovery
                ? "A previous first save stopped before activation. Review and save again, then restart Hermes."
                : "Saving creates a private config and digest for this Hermes profile. Restart Hermes to activate it."
            )
          : snapshot.update_recovery
          ? h("div", null,
              "A later save stopped mid-update. Hermes is using the prior pinned revision. Review and save again to finish repair."
            )
          : snapshot.dashboard_writable
          ? h("div", null, "Saving updates the config and digest together. Restart Hermes to activate it.")
          : h("div", null,
              "Use a private digest sidecar to enable dashboard writes; literal digest environment values are read-only."
            )
      ),
      h("div", { style: styles.row },
        field("State directory", document.state_directory, function (value) {
          props.onDocument(setPath(document, ["state_directory"], value));
        }, { help: "Absolute private directory for receipts and lifecycle state." }),
        h(Button, {
          size: "sm",
          onClick: function () {
            var next = clone(document);
            next.rooms = next.rooms || [];
            next.rooms.push(defaultRoom(document, snapshot.channels || []));
            props.onDocument(next);
          }
        }, "Add room"),
        h(Button, {
          size: "sm",
          ghost: true,
          onClick: function () { setAdvanced(!advanced); }
        }, advanced ? "Room form" : "Advanced JSON")
      ),
      advanced
        ? h("div", null,
            h("textarea", {
              value: raw,
              rows: 28,
              spellCheck: false,
              style: styles.textarea,
              onChange: function (event) { applyRaw(event.target.value); }
            }),
            rawError ? h("div", { style: { color: "var(--color-destructive)", fontSize: "12px" } }, rawError) : null
          )
        : (document.rooms || []).map(function (room, index) {
            return h(RoomEditor, {
              key: index,
              room: room,
              index: index,
              document: document,
              channels: snapshot.channels,
              onDocument: props.onDocument,
              onRemove: removeRoom
            });
          }),
      h("div", { style: styles.row },
        h(Button, {
          size: "sm",
          disabled: !props.dirty || !snapshot.dashboard_writable || Boolean(rawError),
          onClick: function () { props.onSave(false); }
        }, props.saving ? "Saving…" : "Save"),
        h(Button, {
          size: "sm",
          disabled: !snapshot.dashboard_writable || Boolean(rawError),
          onClick: function () { props.onSave(true); }
        }, props.saving ? "Saving…" : (props.dirty ? "Save & restart" : "Restart Hermes")),
        h(Button, { size: "sm", ghost: true, onClick: props.onReload }, "Reload"),
        props.message ? h("span", { style: styles.hint }, props.message) : null
      )
    );
  }

  function ReceiptsPanel(props) {
    var receipts = props.data.receipts || [];
    return h("div", { style: styles.page },
      h("div", { style: styles.row },
        h("span", { style: styles.hint },
          "Newest lifecycle receipts for configured rooms. Full JSON remains available for exact evidence."
        ),
        h(Button, { size: "sm", ghost: true, onClick: props.onReload }, "Refresh")
      ),
      props.message
        ? h("div", { style: styles.status }, props.message)
        : props.data.bootstrap_required
        ? h("div", { style: styles.status },
            "Complete Nunchi room setup before receipts are available."
          )
        : receipts.length
        ? receipts.map(function (receipt, index) {
            var room = receipt._nunchi_room || {};
            var event = receipt.event || receipt.kind || receipt.type || "receipt";
            var time = receipt.created_at || receipt.timestamp || receipt.ts || "";
            return h("details", { key: index, style: styles.receipt },
              h("summary", null,
                event + " · " + (room.platform || "?") + "/" + (room.room_id || "?") +
                (time ? " · " + time : "")
              ),
              h("pre", {
                style: Object.assign({}, styles.textarea, { whiteSpace: "pre-wrap", overflowX: "auto" })
              }, JSON.stringify(receipt, null, 2))
            );
          })
        : h("div", { style: styles.status }, "No receipts found.")
    );
  }

  function NunchiPanel() {
    var [snapshot, setSnapshot] = useState(null);
    var [document, setDocument] = useState(null);
    var [savedDocument, setSavedDocument] = useState(null);
    var [receipts, setReceipts] = useState({ receipts: [] });
    var [tab, setTab] = useState("config");
    var [message, setMessage] = useState("");
    var [saving, setSaving] = useState(false);

    var load = useCallback(function () {
      setMessage("Loading…");
      return fetchJSON(API + "/config").then(function (data) {
        var loadedDocument = clone(data.document);
        if (data.bootstrap_required &&
            (!loadedDocument.rooms || !loadedDocument.rooms.length)) {
          loadedDocument.rooms = [
            defaultRoom(loadedDocument, data.channels || [])
          ];
        }
        setSnapshot(data);
        setDocument(loadedDocument);
        setSavedDocument(clone(data.document));
        setMessage("");
      }).catch(function (error) {
        setMessage("Could not load Nunchi config: " + String(error));
      });
    }, []);

    var loadReceipts = useCallback(function () {
      setMessage("Loading receipts…");
      return fetchJSON(API + "/receipts?limit=100").then(function (data) {
        setReceipts(data);
        setMessage("");
      }).catch(function (error) {
        setMessage("Could not load receipts: " + String(error));
      });
    }, []);

    useEffect(function () { load(); }, [load]);
    useEffect(function () {
      if (tab === "receipts") loadReceipts();
    }, [tab, loadReceipts]);

    function restart(endpoint) {
      setMessage("Restart requested. The dashboard may disconnect briefly.");
      return fetchJSON(endpoint, { method: "POST" }).catch(function (error) {
        setMessage("Config is saved, but Hermes restart failed: " + String(error));
      });
    }

    function save(andRestart) {
      if (!snapshot || !document) return;
      var dirty = JSON.stringify(document) !== JSON.stringify(savedDocument);
      if (!dirty && andRestart) {
        restart(snapshot.restart_endpoint);
        return;
      }
      setSaving(true);
      setMessage("Validating and saving…");
      fetchJSON(API + "/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: snapshot.profile,
          expected_revision: snapshot.revision,
          document: document
        })
      }).then(function (data) {
        setSnapshot(data);
        setDocument(clone(data.document));
        setSavedDocument(clone(data.document));
        setMessage("Saved. Restart Hermes to activate this revision.");
        if (andRestart) return restart(data.restart_endpoint);
      }).catch(function (error) {
        setMessage("Save rejected: " + String(error));
      }).finally(function () {
        setSaving(false);
      });
    }

    var dirty = document && savedDocument &&
      JSON.stringify(document) !== JSON.stringify(savedDocument);
    return h("div", { style: styles.page },
      h("div", { style: Object.assign({}, styles.row, { alignItems: "center" }) },
        h("h2", { style: { margin: 0, flex: "1 1 auto" } }, "Nunchi"),
        h(Button, { size: "sm", ghost: tab !== "config", onClick: function () {
          setTab("config");
        } }, "Configuration"),
        h(Button, { size: "sm", ghost: tab !== "receipts", onClick: function () {
          setTab("receipts");
        } }, "Receipts")
      ),
      !snapshot || !document
        ? h("div", { style: styles.status }, message || "Loading…")
        : tab === "config"
          ? h(ConfigPanel, {
              snapshot: snapshot,
              document: document,
              dirty: dirty,
              saving: saving,
              message: message,
              onDocument: setDocument,
              onSave: save,
              onReload: load
            })
          : h(ReceiptsPanel, {
              data: receipts,
              message: message,
              onReload: loadReceipts
            })
    );
  }

  window.__NUNCHI_REGISTERED__ = true;
  PLUGINS.register("nunchi", NunchiPanel);
})();
