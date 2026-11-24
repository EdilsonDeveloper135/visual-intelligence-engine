"""Run the real pipeline on the sample photo and export what the film shows (real data only)."""
import json, os, sys, time, pathlib, httpx

OUT = pathlib.Path("/out")
c = httpx.Client(base_url="http://127.0.0.1:8080/api/v1", timeout=120)
assert c.post("/auth/login", json={"access_key": os.environ["VIE_ACCESS_KEY"]}).status_code == 200
src = pathlib.Path("/samples/factura_foto_perspectiva.jpg")
oid = os.environ.get("OBS_ID")
if not oid:
    r = c.post("/observations", files=[("files", (src.name, src.read_bytes(), "image/jpeg"))], data={"mode": "full"})
    oid = r.json()["observations"][0]["id"]
t0 = time.time()
while time.time() - t0 < 400:
    d = c.get(f"/observations/{oid}").json()
    if d["status"] in ("completed", "partial", "failed"):
        break
    time.sleep(2)
res = d["result"]
proc = next(a for a in d["assets"] if a["kind"] == "processed")
(OUT / "processed.jpg").write_bytes(c.get(f"/assets/{proc['id']}").content)
(OUT / "photo.jpg").write_bytes(src.read_bytes())
page = res["pages"][0]
data = {
    "observation_id": oid, "status": d["status"],
    "processed_size": [page["width"], page["height"]],
    "steps": [s["name"] for s in page["preprocessing"] if s.get("applied")],
    "quad": page.get("document_quad"),
    "lines": [{"id": l["id"], "text": l["text"], "bbox": l["bbox"]} for l in res["text"]["lines"]],
    "codes": [{"bbox": c_["bbox"], "text": c_["text"]} for c_ in res["codes"]],
    "fields": {k: {"value": v["value"], "source": v["source"], "bbox": v["bounding_box"], "needs_review": v["needs_review"],
                   "reasons": v["review_reasons"], "sources": [{"source": s["source"], "value": s["value"]} for s in v["sources"]]}
               for k, v in res["fields"].items() if v},
    "items": [{"description": i["description"], "amount": i["amount"]} for i in res["items"]],
    "checks": [{"id": ch["id"], "status": ch["status"], "message": ch["message"]} for ch in res["validation"]["checks"]],
    "validation": res["validation"]["status"],
    "document_type": res["document_type"], "description": res["description"],
    "timings": res["metadata"]["timings"], "tokens": res["metadata"].get("vlm_tokens"),
}
(OUT / "factura.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
print(oid, d["status"], len(data["lines"]), "lines")
print(json.dumps({k: v["sources"] for k, v in data["fields"].items() if len(v["sources"]) > 1}, ensure_ascii=False))
print([ (c_["id"], c_["status"]) for c_ in data["checks"] if c_["status"] != "pass"])
