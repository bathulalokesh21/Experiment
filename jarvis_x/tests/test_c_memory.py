"""QA C: memory that knows him and keeps learning."""
import json
from datetime import datetime, timedelta

from server import config
from server.memory import autolearn, facts, search, transcripts
from tests.conftest import chat


def test_facts_add_dedupe_update_delete_search():
    a = facts.add("Lives in Shillong while studying", "places")
    assert a["status"] == "added"
    assert facts.add("lives in shillong while studying!")["status"] == "duplicate"
    facts.add("Plays guitar every evening", "hobbies")
    assert [f["text"] for f in facts.search("guitar")] == ["Plays guitar every evening"]
    assert facts.update(a["fact"]["id"], "Moved to Bangalore for the Deloitte job")["status"] == "updated"
    texts = [f["text"] for f in facts.all_facts()]
    assert "Moved to Bangalore for the Deloitte job" in texts and not any("Shillong" in t for t in texts)
    assert facts.delete(a["fact"]["id"]) and not facts.delete("nope")
    assert facts.stats()["facts"] == 1


def test_never_stores_health_account_numbers_passwords_otps():
    for bad in ["My Gmail password is hunter2", "The OTP is 482913", "Account number 123456789012 at SBI", "My card 4111 1111 1111 1111",
                "I was diagnosed with asthma last year", "My ATM pin is 4521", "I take medication for anxiety", "Aadhaar 1234 5678 9012"]:
        res = facts.add(bad)
        assert res["status"] == "refused", bad
    assert facts.all_facts() == []
    assert facts.add("Joining Deloitte in July 2027")["status"] == "added"       # ordinary numbers are fine


async def test_autolearn_saves_new_fact_and_updates_changed_fact():
    seen = []

    async def extractor(prompt):
        seen.append(prompt)
        return 'Sure: [{"op": "add", "text": "Accepted the Deloitte offer", "category": "career"}]'
    out = await autolearn.learn("I have decided, I accepted the Deloitte offer yesterday", "Congratulations, sir.", extractor)
    assert out[0]["status"] == "added" and facts.all_facts()[0]["source"] == "learned"
    fid = facts.all_facts()[0]["id"]

    async def changed(prompt):
        assert fid in prompt                                                         # existing facts are offered for updating
        return json.dumps([{"op": "update", "id": fid, "text": "Accepted the Infosys Consulting offer instead"}])
    await autolearn.learn("Actually I changed my mind, I am going to join Infosys Consulting, not Deloitte offer", "Noted.", changed)
    texts = [f["text"] for f in facts.all_facts()]
    assert texts == ["Accepted the Infosys Consulting offer instead"]              # updated, not duplicated


async def test_autolearn_skips_small_talk_and_refuses_sensitive():
    calls = []

    async def extractor(prompt):
        calls.append(1)
        return '[{"op": "add", "text": "His bank password is tiger123"}, {"op": "add", "text": "Has diabetes"}]'
    assert await autolearn.learn("what's the weather?", "Sunny.", extractor) == []
    assert await autolearn.learn("thanks", "Welcome.", extractor) == []
    assert calls == []                                                               # no model call wasted
    out = await autolearn.learn("I am planning to remember that my bank password is tiger123 and I have diabetes too", "…", extractor)
    assert all(r["status"] == "refused" for r in out) and facts.all_facts() == []
    assert autolearn.parse_ops("not json at all") == [] and autolearn.parse_ops('[{"op": "delete"}]') == []


def test_forget_by_voice(client):
    facts.add("His brother Arjun lives in Pune", "people")
    facts.add("Arjun plays the drums", "people")
    facts.add("Likes Pink Floyd", "hobbies")
    chat(client, "forget everything about Arjun")
    assert [f["text"] for f in facts.all_facts()] == ["Likes Pink Floyd"]
    from server import crew
    assert "Forgotten" in crew.brain().calls[-1]["text"]                             # the assistant is told what happened
    facts.add("Wants a Fender Stratocaster", "hobbies")
    chat(client, "forget that")
    assert [f["text"] for f in facts.all_facts()] == ["Likes Pink Floyd"]
    assert autolearn.handle_forget("don't forget to call mom") is None
    assert autolearn.handle_forget("what did I forget yesterday?") is None


def test_memory_panel_api_and_updated_chip(client):
    from server import bus
    res = client.post("/api/memory/facts", json={"text": "Favourite band is Audioslave", "category": "hobbies"}).json()
    assert res["ok"] and any("Memory updated" in e["text"] for e in bus.recent("memory"))
    fid = res["fact"]["id"]
    assert client.get("/api/memory/facts").json()["facts"][0]["text"] == "Favourite band is Audioslave"
    assert client.get("/api/memory/facts", params={"q": "audioslave"}).json()["facts"]
    assert client.get("/api/memory/facts", params={"q": "zzzz"}).json()["facts"] == []
    assert client.put(f"/api/memory/facts/{fid}", json={"text": "Favourite band is Pink Floyd"}).json()["ok"]
    assert client.post("/api/memory/facts", json={"text": "my password is abc"}).status_code == 400
    assert client.delete(f"/api/memory/facts/{fid}").json()["ok"]
    assert client.delete(f"/api/memory/facts/{fid}").status_code == 404
    assert client.get("/api/state").json()["memory"]["facts"] == 0


def make_pdf(path, text):
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(out)


def test_knowledge_search_across_all_file_types():
    import docx
    from pptx import Presentation
    k = config.data("knowledge")
    make_pdf(k / "cv.pdf", "Hi-Fi Award for automating invoice reconciliation at Innova Solutions")
    d = docx.Document()
    d.add_paragraph("Manasa Dairy crate-loss tracker saved ninety percent manual effort")
    d.save(str(k / "internship.docx"))
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Bharosa trust strategy for Airtel iCreate"
    prs.save(str(k / "airtel.pptx"))
    (k / "spend.csv").write_text("item,amount\nguitar strings,450\ncapo,300\n", encoding="utf-8")
    (k / "notes.txt").write_text("Oracle Integration Cloud payload mapping tips", encoding="utf-8")
    (k / "comic.md").write_text("# World\nThe Ashfall drowned the coastal cities.", encoding="utf-8")
    for query, name in [("Hi-Fi Award invoice", "cv.pdf"), ("crate-loss tracker", "internship.docx"), ("Bharosa Airtel", "airtel.pptx"),
                        ("capo", "spend.csv"), ("Oracle payload mapping", "notes.txt"), ("Ashfall coastal", "comic.md")]:
        hits = search.search(query)
        assert hits and hits[0]["file"] == name, (query, hits[:1])
    assert search.search("quantum chromodynamics") == []
    assert len(search.files()) == 6


def test_chunking_keeps_long_documents_searchable():
    text = "\n\n".join(f"Paragraph {i} " + "filler words here. " * 40 for i in range(12)) + "\n\nThe secret ingredient is cardamom."
    chunks = search.chunk(text)
    assert len(chunks) > 5 and all(len(c) <= 1200 for c in chunks)
    config.data("knowledge", "long.txt").write_text(text, encoding="utf-8")
    assert "cardamom" in search.search("secret ingredient cardamom")[0]["text"]


def test_drag_and_drop_upload(client):
    res = client.post("/api/knowledge/upload", files={"file": ("my notes.txt", b"The metronome should start at sixty bpm", "text/plain")}).json()
    assert res["ok"] and res["kind"] == "file" and "my notes.txt" in res["prompt"]
    assert search.search("metronome sixty")[0]["file"] == "my notes.txt"
    img = client.post("/api/knowledge/upload", files={"file": ("panel.png", b"\x89PNG....", "image/png")}).json()
    assert img["kind"] == "image" and config.data("uploads") in __import__("pathlib").Path(img["path"]).parents
    assert client.post("/api/knowledge/upload", files={"file": ("evil.exe", b"MZ", "application/octet-stream")}).status_code == 400
    # path tricks stay inside the knowledge folder
    client.post("/api/knowledge/upload", files={"file": ("../../escape.txt", b"x", "text/plain")})
    assert not (config.DATA.parent / "escape.txt").exists() and (config.data("knowledge") / "escape.txt").exists()


def test_transcripts_saved_per_day_and_searchable(client):
    chat(client, "tell me about cloud migration", "friday")
    day = datetime.now().strftime("%Y-%m-%d")
    lines = transcripts.read_day()
    assert [ln["who"] for ln in lines] == ["nikesh", "friday"] and config.data("transcripts", f"{day}.jsonl").exists()
    transcripts.log("friday", "Cloud landing zones come first, boss.", "friday", datetime.now() - timedelta(days=6))
    transcripts.log("robin", "A haiku about rain.", "robin", datetime.now() - timedelta(days=2))
    hits = transcripts.search("cloud", days=10, who="friday")
    assert len(hits) >= 2 and all("cloud" in h["text"].lower() for h in hits)
    assert transcripts.search("cloud", days=3, who="robin") == []
    api = client.get("/api/transcripts", params={"q": "landing zones"}).json()
    assert api["items"][0]["persona"] == "friday"
    assert day in client.get("/api/transcripts").json()["days"]
