# Argus Breakdown Report

Audit tanggal: 2026-08-12 · Argus v1.1.0 · Python 3.12
Jangkauan: `src/` (63 file), `tests/` (38 file), `examples/`, tooling config.

---

## 0. Ringkasan eksekutif

| Area | Status |
|---|---|
| Test suite | 475 test **passed** (17.4s), coverage **88%** |
| ruff | **1142 errors** (src 804 · tests 330 · examples 8) — 634 auto-fixable |
| mypy | **140 errors di 21 file** (strict-flags ON, banyak file lolos karena implisit) |
| CI | Hanya menjalankan `pytest`. **ruff/mypy/black tidak ditegakkan** di CI |
| Bug runtime yang terbukti | 3 (NameError x2, priority event mati) |
| Gap coverage kritis | `gateway/server.py` **25%**, `cli/main.py` **40%**, subprocess sandbox path **~0%** |

Kesimpulan satu kalimat: **fitur lengkap dan test hijau, tapi kualitas kode (lint/typing) dan jalur HTTP/isolation (gateway, subprocess sandbox) adalah titik lemah terbesar — plus 3 bug runtime nyata yang lolos test.**

---

## 1. Bugs & lint issues

### 1.1 Bug runtime (terbukti, lolos test suite)

| # | Severity | Lokasi | Bug |
|---|---|---|---|
| B1 | HIGH | `src/argus/dashboard/__init__.py:219` | `create_dashboard_store()` tanpa argumen → **NameError: `Path` tidak di-import**. Dipastikan via repro. Test hanya memanggil dengan path eksplisit. |
| B2 | HIGH | `src/argus/branding.py:133` | `render_logo_jpeg` memakai `Optional[str]` tapi `Optional` tidak di-import → **NameError saat fungsi dipanggil**. Terdeteksi mypy `name-defined`. |
| B3 | HIGH | `src/argus/common/events.py:36` + `sandbox.py:176,217,256` + `engine.py:158` | `Event(..., priority=...)` — model `Event` **tidak punya field `priority`**, pydantic v2 default `extra="ignore"` → kwarg **diam-diam dibuang**. Akibat: sistem prioritas event mati; event `capability.execution.failed` (HIGH) tidak pernah diberi prioritas. Diuji: `e.priority` → `NOT PRESENT`, `metadata` kosong. |

### 1.2 Bug laten (jalur tak teruji, kemungkinan rusak)

| # | Severity | Lokasi | Masalah |
|---|---|---|---|
| B4 | MED | `gateway/server.py:323` | `@WebMiddleware` dipakai ke *method* (`self, request, handler`). Bila aiohttp terpasang, signature middleware akan salah (self menelan argumen request). Jalur ini **0% teruji** (aiohttp tak ada di dev-deps). |
| B5 | MED | `runtime/sandbox.py:287-291` | Script subprocess meng-import `resource` (modul **Unix-only**). Klaim cross-platform (Windows/macOS) gagal untuk mode `SUBPROCESS`. CI menjalankan Windows/macOS tapi path ini tak di-cover. |
| B6 | MED | `common/lifecycle.py:188` & `reflection/loop.py:192` | `asyncio.run()` di dalam method sync → `RuntimeError` bila dipanggil dari dalam event loop yang berjalan (event bus, gateway, orchestrator). |
| B7 | LOW | `events.py:43` | `datetime.utcnow` deprecated (muncul `DeprecationWarning` di output test). |
| B8 | LOW | `gateway/server.py:229` | Loop var `field` men-shadow import `dataclasses.field`. |
| B9 | LOW | `observability/store.py:270-272` | `close()` set `self._conn = None` tanpa guard; pemakaian setelah close → crash. |

### 1.3 ruff — breakdown (1142 errors)

| Rule | Jumlah | Makna |
|---|---|---|
| UP045 | 202 | `Optional[X]` → `X \| None` (mekanis) |
| PLR2004 | 134 | Magic value dalam komparasi |
| F401 | 110 | Import tak terpakai (banyak di tests) |
| COM812 | 81 | Kurang trailing comma |
| TRY003 | 64 | Pesan panjang di `raise` polos |
| UP017 | 60 | `datetime.utcnow()` → `datetime.now(UTC)` |
| E501 | 55 | Baris >100 char |
| I001 | 53 | Import tidak terurut |
| PLC0415 | 53 | `import` di dalam fungsi |
| W292 | 44 | Tidak ada newline akhir file |
| + 45 rule lain | ~286 | lihat `ruff check src tests examples --statistics` |

Distribusi: `src/` 804 · `tests/` 330 · `examples/` 8. 634 auto-fixable.

### 1.4 mypy — breakdown (140 errors di 21 file)

`strict_optional`/`disallow_untyped_defs` aktif, tapi `disallow_any`/`strict` penuh tidak. Hotspot:

| File | Errors | Catatan |
|---|---|---|
| `gateway/server.py` | 63 | Stub aiohttp: `WebRequest`/`WebResponse` jadi `object` saat tak terpasang |
| `capability/engine.py` | 11 | `priority=` call-arg, `_capability_spec` attr-defined, implicit Optional |
| `secretvault/vault.py` | 7 | `salt`, `_fernet` union-None |
| `orchestrator/communication.py` | 6 | |
| `observability/logs.py` | 6 | |
| `runtime/sandbox.py` | 5 | `priority=` call-arg, `exit_code: int\|None` |
| `cli/main.py`, `branding.py`, `_smoke.py` | 4-5 | `Optional` name-defined, untyped defs |
| 11 file lain | 1-3 | |

Tipe error dominan: `no-untyped-def` (29), `no-any-return` (28), `valid-type` (18), `attr-defined` (13), `assignment` (10).

### 1.5 Issue config/tooling

- `pyproject.toml:62-66` — konfigurasi ruff di section top-level (`select`/`ignore`) → **deprecated**, harus `[tool.ruff.lint]`. Diabaikan dengan warning.
- Rule `D203` vs `D211`, `D212` vs `D213` saling kontradiksi → ruff memilih salah satu diam-diam.
- **CI (`.github/workflows/ci.yml`) hanya pytest** — tidak ada job ruff/mypy/black. Ini kenapa 1142+140 error lolos merge.

---

## 2. Komponen terimplementasi tapi belum ada test-nya

Coverage 88% total, tapi titik-titik ini "ada tapi nyaris tak diuji":

| Komponen | Coverage | Detail |
|---|---|---|
| `gateway/server.py` (HTTP server) | **25%** | Hanya config + konstruktor yang diuji (`test_server.py`). Seluruh route (`/health`, `/api/v1/*`), auth flow, CORS, broadcast tak diuji. **aiohttp tidak ada di dev-deps**, jadi kode ini tak pernah dieksekusi sekali pun di CI. |
| `cli/main.py` | **40%** | `logo --render`, `ask`, `curator`, `dashboard`, `chat` hampir tak diuji. |
| `runtime/sandbox.py` (mode SUBPROCESS) | 77% | Baris 279–399 (isolasi subprocess) **tak di-cover** — fitur keamanan inti tak teruji. |
| `extension/rpc.py` | 74% | Path error/validate kontrak eksekusi ekstensi. |
| `orchestrator/communication.py` | 77% | `request_response`, broadcast, unsubscribe di tengah aliran. |
| `dashboard/__init__.py` | 94% | `serve_dashboard`/`run_dashboard_in_thread` (baris 195–198) tak diuji. |
| `runtime/workflow.py` | 86% | Pause/resume/checkpoint edge (106–118), restore. |
| `events.py` | 87% | Dead-letter, priority, flush (127–133, 201–219). |

### Yang *tidak* punya file test sendiri
Semua modul runtime punya coverage via `test_runtime_manager.py` (state, transaction, lock, scheduler) dan `test_orchestrator.py` (communication, agent) — jadi **tidak ada modul nol-test**, tapi beberapa path penting kosong.

---

## 3. Gap vs spesifikasi (BLUEPRINT_COMPLIANCE.md)

`docs/BLUEPRINT_COMPLIANCE.md` menyatakan "all 11 phases done". Verifikasi lapangan:

| Klaim | Realita |
|---|---|
| Streaming Manager "done" | Ada `runtime/streaming.py`, tapi **tidak dihubungkan** ke provider/orchestrator — dead code tak terpakai. |
| Runtime Monitor "done" | `runtime/monitor.py` ada, tapi tidak dijalankan di mana pun. |
| Intent Parser "done" | `brain/intent.py` ada, tapi hanya rule-based sederhana; tidak diintegrasikan ke goal engine (spesifikasi Part 2 minta "folded into Goal Engine"). |
| Gateway "WebSocket support" (docstring) | **Tidak ada route ws** di `server.py` — klaim di docstring tidak sesuai kode. |
| Config terintegrasi | `ArgusSettings` punya 9 sub-config (`EventBusConfig`, `SchedulerConfig`, `CapabilityConfig.ranking_weights`, dll) tapi **tidak satu pun dikonsumsi** modul runtime/capability/events. Settings = dead weight. |
| Verification stage | Ada `verification/` (5 checks), tapi **tidak dipanggil** oleh engine/orchestrator — pipeline "Verify Before Respond" tidak benar-benar terhubung. |
| Provider generik | `brain/provider.py` meng-hardcode env `HERMES_CUSTOM_LOCALHOST_20128_API_KEY`, base_url default `localhost:20128`, model `Cadangan` — sisa-sisa proyek lain menempel di framework. |
| Gateway rate-limit | Tidak ada (spec §Part 4 kemungkinan implisit). |
| Dashboard auth | Dashboard bind `127.0.0.1`, tanpa auth — OK untuk lokal, tapi tak ada kontrol sama sekali. |

**Catatan**: `CHANGELOG [Unreleased]` menyebut "448 tests total", `BLUEPRINT` menyebut 448, `README` menyebut 369 → angka aktual **475**. Dokumentasi tidak sinkron.

---

## 4. Refactor opportunities

1. **Dua pola SQLite berbeda.** `observability/store.py` pakai koneksi persisten + `threading.Lock`; `memory/store.py` buka–tutup koneksi tiap operasi. Satukan menjadi satu helper DB (conn-per-op atau pool).
2. **Bug `Event.priority`** → tambahkan field `priority` ke model `Event` (atau paksa via `metadata`), lalu hapus 4+ pemanggilan `priority=` yang diam-diam dibuang. Sekalian satu kelas sumber perbaikan.
3. **`capability/engine.py`**:
   - `Sandbox` baru dibuat per attempt (baris 243) → reuse satu instance.
   - Akses `self.sandbox._audit_buffer.append(...)` (baris 277) → sediakan method publik `merge_audit()`.
   - `func._capability_spec` / `func._capability_policy` (baris 344-345) → `WeakKeyDictionary` atau side-registry.
4. **`secretvault/vault.py`**: parsing header salt/iterations diulang di `_load_salt_from_vault` & `_load_vault` (double read file); `except Exception` kosong tanpa log (TRY400) menelan error; `rotate_master_key` menciptakan `plaintext_secrets` tak terpakai (F841) — sekalian rawan salah paham.
5. **Duplikasi JSON sidecar**: `curator/__init__.py` dan `knowledge/__init__.py` punya pola lock+load+save+tmp-replace yang identik → ekstrak `JSONSidecarStore`.
6. **`Optional[X]` vs `X | None`** campur (202x UP045) + `import` dalam fungsi (53x) + magic value (134x) → satu pass `ruff --fix` + konstanta.
7. **`common/logging.py` `_NamedLogger`** — wrapper hanya untuk `.name`; bisa pakai `structlog.get_logger(name).bind(name=...)` atau subclass ringan.
8. **`orchestrator/communication.py` `broadcast()`** memutasi `message.to_agent = ""` pada objek pemanggil → efek samping tak terduga.
9. **`dashboard/__init__.py`**: docstring ganda (baris 219-220), `import string` di dalam fungsi → module-level.

---

## 5. Performance concerns

| # | Area | Masalah |
|---|---|---|
| P1 | `memory/store.py:117-129` | **Koneksi SQLite baru per operasi** (add/search/update). Untuk beban agent normal mahal; untuk bulk sangat mahal. |
| P2 | `observability/store.py` | `commit()` **setiap INSERT** (fsync per baris) + lock global menyerialkan semua collector. |
| P3 | `secretvault/vault.py` | `auto_save=True` → **re-encrypt + tulis seluruh vault ke disk** di tiap `set()`/`delete()` di bawah lock. |
| P4 | `curator`/`knowledge` | Tulis **seluruh file JSON** setiap record (lock penuh). |
| P5 | `brain/provider.py:93` | `urllib.request` **sinkron blocking** → memblokir event loop bila dipakai dari async context (orchestrator). |
| P6 | `orchestrator/orchestrator.py:161` | **Busy-wait polling** `while ... : await asyncio.sleep(0.1)` → ganti `asyncio.Event`/Condition (ASYNC110). |
| P7 | `memory/store.py:300-345` | `search_vector` memuat **semua** embedding ke Python lalu cosine brute-force O(n); `search_fts` + filter memuat semua baris match (unbounded). |
| P8 | `runtime/sandbox.py:426-429` | Timeout `wait_for` di mode THREAD **tidak membatalkan thread** yang jalan — thread liar terus berjalan (kebocoran resource). |
| P9 | `observability/store.py` | **Tidak ada retention/archival** → DB tumbuh tanpa batas. |
| P10 | `events.py:197` | Worker polling queue dgn `wait_for(timeout=0.1)` + `asyncio.gather` per event → overhead task tinggi pada throughput besar. |
| P11 | `capability/engine.py:243` | Sandbox baru per attempt → alokasi berulang. |

---

## 6. Prioritas: segera vs nanti

### 🔴 SEGERA (blocking quality)
1. **B1, B2, B3** — perbaiki 3 bug runtime (dashboard `Path`, branding `Optional`, `Event.priority`).
2. **CI** — tambahkan job `ruff check` + `mypy src` (fix dulu 634 auto-fixable) agar regresi berhenti masuk.
3. **B4/B5** — `gateway/server.py` jalur aiohttp (perbaiki middleware, tambah aiohttp ke dev-deps, tulis test route) dan sandbox subprocess tanpa `resource` agar klaim cross-platform benar.
4. **P6** — busy-wait di orchestrator (bisa bikin kagok di production).
5. Rapi-kan config lint di `pyproject.toml` (`[tool.ruff.lint]`) + pilih rule yang saling kontradiksi.

### 🟡 NANTI (quality debt)
6. **Test gap**: HTTP gateway (25%), CLI (40%), subprocess sandbox — tambah test + dependency `aiohttp` (test-only) atau mock.
7. **P1–P4** — strategi DB/IO: batch commit, simpan-dijeda, WAL, koneksi reuse.
8. **Integrasi spesifikasi**: wiring `ArgusSettings` → modul; sambungkan `streaming`, `monitor`, `verification`, `intent` ke alur nyata; hapus dead-code klaim WebSocket bila tak akan diimplementasi.
9. **Refactor 3–9** (section 4) — kebanyakan mekanis, bisa bertahap.
10. **Dokumentasi** — samakan angka test (README 369 / BLUEPRINT 448 / aktual 475); sinkronkan CHANGELOG.

---

## 7. Lampiran: data mentah

```
pytest          : 475 passed, 182 warnings, 17.4s
coverage        : 88% (4718 stmts, 564 miss)
ruff            : 1142 errors (src 804 / tests 330 / examples 8); 634 fixable
mypy src        : 140 errors in 21 files
file terbanyak  : gateway/server.py 63 · capability/engine.py 11 · secretvault/vault.py 7
src/argus       : 63 file .py, 14.7k baris (src+tests)
```
