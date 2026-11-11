"""QA B: the crew."""
import asyncio

import pytest

from server import app as app_module
from server import config, crew, voice
from tests.conftest import chat


def test_three_personas_models_voices_addresses():
    p = crew.PERSONAS
    assert [p[k]["model"] for k in crew.ORDER] == ["opus", "sonnet", "haiku"]
    assert [p[k]["address"] for k in crew.ORDER] == ["sir", "boss", "Love"]
    assert p["jarvis"]["greeting"] == "Welcome home, sir."
    assert len({p[k]["colour"] for k in p}) == 3 and len({p[k]["form"] for k in p}) == 3
    assert voice.settings_for("jarvis")["voice"].startswith("en-GB") and voice.settings_for("friday")["voice"].startswith("en-IE")
    assert voice.settings_for("robin")["voice"].startswith("en-") and "ja-" not in voice.settings_for("robin")["voice"]
    for pid in crew.ORDER:
        assert all(p[pid]["address"].lower() in a.lower() for a in p[pid]["acks"])


def test_system_prompt_has_profile_preferences_rules_and_learned_facts():
    from server.memory import facts
    facts.add("Accepted the Deloitte offer", "career")
    for pid in crew.ORDER:
        prompt = crew.system_prompt(pid)
        assert "Nikesh Bathula" in prompt and "IIM Shillong" in prompt          # profile/me.md
        assert "Casual and direct" in prompt                                     # preferences.md
        assert "Accepted the Deloitte offer" in prompt                           # learned facts
        assert "[FILL]" not in prompt
        assert "English only" in prompt and "approval" in prompt.lower()
        assert f"'{crew.PERSONAS[pid]['address']}'" in prompt
        assert "untrusted" in prompt


def test_effort_reaches_the_model_but_never_haiku():
    assert crew.effort_for("jarvis", "deep") == "high" and crew.effort_for("friday", "fast") == "low"
    assert crew.effort_for("jarvis", "med") == "medium" and crew.effort_for("jarvis", "auto") is None
    for effort in ("auto", "fast", "med", "deep"):
        assert crew.effort_for("robin", effort) is None


def test_humor_labels_and_message_wrapping():
    assert [crew.humor_label(v) for v in (0, 20, 50, 70, 95)] == ["Serious", "Dry wit", "Playful", "Banter", "Chaos"]
    wrapped = crew.wrap_message("hello", 70, {"people": 2, "mode": "drill"})
    assert 'humor="70"' in wrapped and 'humor_label="Banter"' in wrapped and 'people_in_view="2"' in wrapped and wrapped.endswith("hello")


def test_sdk_options_match_the_installed_sdk():
    """Build real ClaudeAgentOptions (no connection): catches renamed/removed SDK parameters."""
    from server.tools import registry
    brain = crew.SdkBrain()
    opts = brain._options("jarvis", "high")
    assert opts.model == "opus" and opts.effort == "high" and opts.include_partial_messages is True
    assert opts.tools == ["WebSearch", "WebFetch", "Read"]            # no shell, no file writes
    assert "Read" not in opts.allowed_tools                            # Read always goes through the permission gate
    assert "mcp__jarvis__get_time" in opts.allowed_tools and len(opts.allowed_tools) == len(registry.all_tools()) + 2
    assert opts.can_use_tool is crew.permission_gate and opts.setting_sources == []
    assert "jarvis" in opts.mcp_servers
    assert brain._options("robin", None).model == "haiku" and brain._options("friday", None).model == "sonnet"


async def test_permission_gate_limits_read_and_blocks_everything_else():
    inside = config.data("screens", "s.png")
    assert (await crew.permission_gate("Read", {"file_path": str(inside)}, None)).behavior == "allow"
    assert (await crew.permission_gate("Read", {"file_path": str(config.data("knowledge", "cv.pdf"))}, None)).behavior == "allow"
    for bad in [str(config.data("google", "token.json")), str(config.ROOT / ".env"), str(config.data("screens", "..", "google", "token.json")),
                "C:\\Windows\\system.ini", "/etc/passwd"]:
        assert (await crew.permission_gate("Read", {"file_path": bad}, None)).behavior == "deny", bad
    for tool in ("Bash", "Write", "Edit", "Glob", "Task"):
        assert (await crew.permission_gate(tool, {}, None)).behavior == "deny"
    assert (await crew.permission_gate("mcp__jarvis__get_time", {}, None)).behavior == "allow"
    assert (await crew.permission_gate("WebSearch", {}, None)).behavior == "allow"


def test_chat_streams_and_keeps_separate_memory_per_assistant(client):
    text, events = chat(client, "hello there", "jarvis")
    assert "sir" in text and any(e["type"] == "delta" for e in events) and any(e["type"] == "timing" for e in events)
    chat(client, "second thing", "jarvis")
    chat(client, "only one for friday", "friday")
    j, _ = chat(client, "do you remember our chat", "jarvis")
    f, _ = chat(client, "do you remember our chat", "friday")
    r, _ = chat(client, "do you remember our chat", "robin")
    assert "3 things" in j and "2 things" in f and "1 things" in r
    assert "boss" in f and "Love" in r


def test_humor_effort_and_people_count_reach_the_brain(client):
    client.post("/api/vision/context", json={"people": 2})
    chat(client, "hi", "jarvis", humor=88, effort="deep")
    chat(client, "hi", "robin", humor=10, effort="deep")
    calls = crew.brain().calls
    assert calls[0]["humor"] == 88 and calls[0]["effort"] == "high" and calls[0]["context"]["people"] == 2 and calls[0]["model"] == "opus"
    assert calls[1]["effort"] is None and calls[1]["model"] == "haiku"


def test_settings_are_the_default_for_chat(client):
    client.put("/api/settings", json={"humor": 77, "effort": "fast"})
    chat(client, "hi", "friday")
    assert crew.brain().calls[-1]["humor"] == 77 and crew.brain().calls[-1]["effort"] == "low"
    assert client.put("/api/settings", json={"humor": 500, "effort": "nonsense", "evil": 1}).json()["settings"]["humor"] == 100


def test_empty_message_is_refused(client):
    assert client.post("/api/chat", json={"persona": "jarvis", "text": "  "}).status_code == 400


def test_usage_status_and_checkpoints_announced_once(client):
    events = app_module.note_usage({"status": "allowed", "utilization": None}, "jarvis")
    assert events == [] and app_module.state["usage"]["percent"] is None and app_module.state["usage"]["status"] == "allowed"
    said = []
    for pct in (0.10, 0.26, 0.30, 0.52, 0.86, 0.86, 0.91, 1.0, 1.0):
        said += [e["value"] for e in app_module.note_usage({"status": "allowed_warning", "utilization": pct, "resets_at": 111}, "friday")]
    assert said == [25, 50, 85, 90, 100]                               # each exactly once
    assert app_module.state["usage"]["percent"] == 100
    line = app_module.CHECKPOINT_LINES["friday"][85]
    assert "boss" in line
    # a new usage window starts the announcements again
    assert [e["value"] for e in app_module.note_usage({"status": "allowed", "utilization": 0.3, "resets_at": 222}, "robin")] == [25]


def test_checkpoint_arrives_after_the_answer(client):
    class Brain(crew.FakeBrain):
        async def stream(self, persona_id, text, effort="auto", humor=40, context=None):
            yield {"type": "usage", "status": "allowed_warning", "utilization": 0.87, "resets_at": 5}
            yield {"type": "delta", "text": "Here is the answer."}
            yield {"type": "done", "text": "Here is the answer."}
    crew.set_brain(Brain())
    _, events = chat(client, "question")
    kinds = [e["type"] for e in events]
    assert kinds.index("checkpoint") > kinds.index("delta") and kinds[-1] == "done"
    assert events[kinds.index("checkpoint")]["value"] == 85 and "sir" in events[kinds.index("checkpoint")]["text"]


def test_brain_errors_become_plain_english(client):
    class Broken(crew.FakeBrain):
        async def stream(self, *a, **k):
            raise RuntimeError("Invalid API key · Please run /login")
            yield  # pragma: no cover
    crew.set_brain(Broken())
    _, events = chat(client, "hello")
    err = next(e for e in events if e["type"] == "error")
    assert "log" in err["message"].lower() and "claude" in err["message"].lower()
    assert "terminal" in crew.friendly_error(Exception("cannot write to terminal")).lower()
    assert "limit" in crew.friendly_error(Exception("rate_limit")).lower()


def test_api_key_is_stripped(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-vanish")
    config.load_env()
    import os
    assert "ANTHROPIC_API_KEY" not in os.environ


async def test_voice_first_bytes_retry_then_persona_matched_fallback():
    attempts = []

    async def flaky(text, voice_name, rate, pitch):
        attempts.append(voice_name)
        if len(attempts) < 3:
            raise ConnectionError("no audio")
        yield b"AUDIO"
    voice.set_synth(flaky)
    out = b"".join([c async for c in voice.synth("friday", "Hello, boss.")])
    assert out == b"AUDIO"
    cfg = voice.settings_for("friday")
    assert attempts == [cfg["voice"], cfg["voice"], cfg["fallback"]]     # retry once, then her own fallback
    assert "Ryan" not in cfg["fallback"] and "Thomas" not in cfg["fallback"]

    async def dead(text, voice_name, rate, pitch):
        raise ConnectionError("down")
        yield b""  # pragma: no cover
    voice.set_synth(dead)
    with pytest.raises(voice.VoiceError):
        async for _ in voice.synth("jarvis", "Hello."):
            pass

    async def empty(text, voice_name, rate, pitch):
        return
        yield b""  # pragma: no cover
    voice.set_synth(empty)
    with pytest.raises(voice.VoiceError):                                 # never return empty audio
        async for _ in voice.synth("jarvis", "Hello."):
            pass


def test_voice_cleaning_env_overrides_and_own_clips(monkeypatch):
    assert voice.clean_for_speech("**Well,** sir, see https://x.com/a `code` — done.") == "Well sir, see a link code, done."
    assert voice.clean_for_speech("- one\n- two") == "one two"
    monkeypatch.setenv("ROBIN_VOICE", "en-GB-SoniaNeural")
    monkeypatch.setenv("ROBIN_RATE", "-10%")
    assert voice.settings_for("robin")["voice"] == "en-GB-SoniaNeural" and voice.settings_for("robin")["rate"] == "-10%"
    clip = config.data("voices", "jarvis", "clips", "welcome_home_sir.mp3")
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"MYVOICE")
    assert voice.own_clip("jarvis", voice.clean_for_speech("Welcome home, sir.")) == b"MYVOICE"


def test_tts_route_serves_audio_and_fails_honestly(client):
    res = client.get("/api/tts", params={"persona": "robin", "text": "There you are, Love."})
    assert res.status_code == 200 and res.content[:4] == b"RIFF" and len(res.content) > 1000
    assert client.get("/api/tts", params={"persona": "robin", "text": "***"}).status_code == 503

    async def dead(text, voice_name, rate, pitch):
        raise ConnectionError("down")
        yield b""  # pragma: no cover
    voice.set_synth(dead)
    assert client.get("/api/tts", params={"persona": "jarvis", "text": "hello"}).status_code == 503


def test_prewarm_and_interrupt_exist(client):
    asyncio.run(crew.FakeBrain().prewarm())
    assert client.post("/api/stop", json={"persona": "jarvis"}).json()["ok"]
