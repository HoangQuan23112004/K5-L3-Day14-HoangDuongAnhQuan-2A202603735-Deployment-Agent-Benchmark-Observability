# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích trực tiếp từ các file JSON (`reports/`), CSV (`benchmark-results/`), log JSON và ảnh chụp thực tế (`screenshots/`).

**Họ tên:** Hoàng Dương Anh Quân (MSSV: 2A202603735)  
**Ngày chạy:** 26/11/2026  
**Môi trường:** Windows + WSL2 Ubuntu 22.04, Docker Desktop (Linux containers), Python 3.10/3.11  

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Đảm bảo 95% người dùng nhận phản hồi dưới 0.5 giây (ngưỡng trải nghiệm tương tác nhanh), phù hợp với mock LLM có latency nền ~150–220 ms. |
| Error rate `/ask` | `< 2.0 %` | Cho phép error budget 2% cho lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0.01`), đồng thời phát hiện sớm khi tỉ lệ lỗi vượt ngưỡng bình thường. |
| Accuracy trên golden dataset | `≥ 100 %` (sau khi sửa KB; chất lượng tối thiểu `≥ 80%`) | Ngăn regression về chất lượng câu trả lời trước khi merge/deploy phiên bản agent mới. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.68 | 194.7 | 1662.7 | 1692.9 | 0.33% | ❌ FAIL (p95 > 500ms) |
| 10 | 34.51 | 191.6 | 224.6 | 1704.0 | 2.33% | ❌ FAIL (error rate > 2.0%) |
| 50 | 105.13 | 197.1 | 242.5 | 1713.2 | 1.67% | ✅ PASS |
| 100 | 57.31 | 592.8 | 3577.9 | 3847.9 | 2.33% | ❌ FAIL (p95 > 500ms & error > 2%) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ `c=1` → `10` → `50`, RPS tăng mạnh (`3.68` → `34.51` → `105.13 req/s`) nhờ FastAPI chạy async non-blocking nên nhiều request chờ I/O song song được. Nhưng khi tăng lên `c=100`, hệ thống bắt đầu bão hòa (hàng đợi event loop + socket/connection trên 1 process uvicorn), khiến latency tăng vọt (`p50` lên `592.8 ms`, `p95` lên `3577.9 ms`) và RPS tụt ngược xuống `57.31 req/s`.

### 2.2 Tail latency (`concurrency=20`, 300 requests/mức)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 190.6 | 218.3 | 224.3 |
| 0.03 (mặc định) | 239.1 | 221.4 | 1692.0 |
| 0.1 | 352.1 | 1685.0 | 1717.4 |

**Nhận xét:** **p99** (và **p95** khi tỉ lệ chậm vượt 5%) nhạy nhất với request chậm bất thường. Ở `MOCK_SLOW_RATE=0.03`, `avg` chỉ tăng nhẹ từ `190.6 ms` lên `239.1 ms` (trông có vẻ bình thường), nhưng `p99` nhảy vọt hơn 7 lần lên `1692.0 ms`. Khi `MOCK_SLOW_RATE=0.1` (10% request chậm), `avg` mới là `352.1 ms` (vẫn dưới 500ms), nhưng `p95` đã vọt lên `1685.0 ms` và vi phạm SLO. Vì vậy SLO phải đặt theo **p95/p99** thay vì average để không che giấu tail latency mà người dùng thật đang chịu đựng.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.0 | 109.1 | 114.8 |
| Tổng cost (USD) | $0.000388 | $0.000762 | $0.000801 |
| Cost / câu đúng (USD) | $0.00038835 | $0.00003627 | $0.00003481 |
| Quality gate | ❌ FAIL | ✅ PASS (≥80%) | ✅ PASS (≥100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách đã sửa (`KNOWLEDGE_BASE` trong `mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry về `jwt`, `xác thực`, `api key` giải thích JWT là JSON Web Token có chữ ký số và thời gian hết hạn, khác API key tĩnh. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry về `hpa`, `kubernetes`, `autoscaling` giải thích Kubernetes HPA scale dựa trên CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 tốn khoảng gấp đôi số token (`109.1–114.8` vs `56.0`) và tổng chi phí (`$0.000762–$0.000801` vs `$0.000388`), đồng thời latency p50 tăng thêm ~30 ms (`190.4 ms` vs `160.1 ms`) do có thêm bước retrieval ngữ cảnh.
- Tuy nhiên, độ chính xác nhảy từ **4.3% → 100%**, khiến **cost / câu đúng** của v2 (`$0.00003481`) **rẻ hơn hơn 11 lần** so với v1 (`$0.00038835`). Dùng "cost / câu đúng" phản ánh đúng hiệu quả thực tế hơn là chỉ nhìn tổng chi phí.
- **Tích hợp CI Quality Gate:** Trong GitHub Actions (hoặc CI pipeline), chạy `python eval/run_eval.py --url ... --min-accuracy 1.0 --baseline reports/eval_v2.json`; vì script trả exit code `1` khi accuracy dưới ngưỡng hoặc có bất kỳ câu nào regression, CI job sẽ tự động fail và chặn merge PR.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception` / HTTP 503): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với 2+ alert đang **firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.25` | `AgentHighErrorRate` (`severity: critical`, error rate ~24.0%) | ~1 phút 15 giây (`for: 1m` + scrape interval) | Error Rate (%) & HTTP Status Codes |
| B | `MOCK_SLOW_RATE=0.35` | `AgentHighLatencyP95` (`severity: warning`, p95 ~1.91s) | ~2 phút 15 giây (`for: 2m` + scrape interval) | Request Latency (p50 / p95 / p99) |
| C | `LLM_MODEL=mock-llm-large` (hoặc tải cao) | `LLMCostBurnRateHigh` (`severity: warning`, burn rate `$3.95/giờ > $2/giờ`) | ~2 phút (`for: 2m`) | LLM Cost Burn Rate ($/h) & Tokens/sec |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` (`severity: critical`, `up{job="agent"} == 0`) | ~40 giây (`for: 30s` + scrape interval) | Active Agent Instances (`up`) |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | N/A | Không có panel hạ tầng nào báo đỏ (chỉ thấy `agent_info` đổi sang `v1`, token/latency giảm nhẹ) |

**Thí nghiệm E không làm alert nào firing. Phát hiện loại sự cố này trong production bằng cách nào?**
- Các alert hạ tầng (Golden Signals) chỉ phát hiện lỗi HTTP 5xx, latency chậm hoặc sập container, nhưng không biết câu trả lời bị giảm chất lượng (silent degradation).
- Để phát hiện sự cố này cần kết hợp: **(1)** chạy **automated eval / quality gate** trên golden dataset trong CI/CD trước khi deploy; **(2)** chạy **online evaluation / LLM-as-a-judge** trên mẫu traffic production định kỳ; và **(3)** theo dõi **business/product metrics** (tỉ lệ thumbs-down của user, tỉ lệ hỏi lại/retry, và alert khi `agent_info{version}` thay đổi bất thường).

### 4.3 Debug bằng trace

Trace chậm nhất chọn được trong Jaeger (`screenshots/jaeger-slow-trace.png`):

- `trace_id`: `c86e360c4daf9acde634ab9207df3a01`
- Tổng thời gian: `1761.77 ms` (`POST /ask`, log ghi `1761.2 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (`1686.30 ms`, chiếm **95.7%** tổng thời gian; trong khi `agent.retrieve_context` chỉ mất `18.33 ms`, ~1.0%).
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T09:22:51.587264+00:00", "level": "INFO", "service": "observable-agent", "instance": "0742e455ba08", "event": "http_request", "trace_id": "c86e360c4daf9acde634ab9207df3a01", "span_id": "67de43c6dabc440d", "request_id": "39db1d2e68eb", "method": "POST", "route": "/ask", "status": 200, "ms": 1761.2}
```

Trace lỗi HTTP 503 trong Jaeger (`screenshots/jaeger-error-trace.png`):
- `trace_id`: `7af799a73c040116a5db8cedebf713fd` (`POST /ask`, `98.6 ms`, `status: 503`):
```json
{"ts": "2026-11-26T09:20:50.585237+00:00", "level": "INFO", "service": "observable-agent", "instance": "0742e455ba08", "event": "http_request", "trace_id": "7af799a73c040116a5db8cedebf713fd", "span_id": "0463b2a9bda12c48", "request_id": "2ef26fc0c2c1", "method": "POST", "route": "/ask", "status": 503, "ms": 98.6}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu `POST /ask` trích trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`:

| Số instance | RPS (`POST /ask` / Aggregated) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.62 (65.40) | 190 | 220 | 1700 | 67 / 7216 (0.93%) |
| 3 | 59.03 (65.17) | 190 | 220 | 1700 | 69 / 7160 (0.96%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không** làm giảm p95/p99 và cũng không tăng RPS ở mức tải 100 users này. Nguyên nhân là do **nút thắt (bottleneck) nằm ở thời gian chờ I/O của upstream LLM** (`await asyncio.sleep(...)` + `MOCK_SLOW_RATE=0.03` tạo tail latency ~1700ms) và thời gian think-time giữa các request của Locust user, chứ không phải do CPU của 1 container agent bị bão hòa. Vì FastAPI xử lý async nên 1 instance đã đủ phục vụ ~65 RPS nhẹ nhàng; việc scale lên 3 instance chủ yếu giúp tăng **high availability** (chịu lỗi khi 1 instance chết) và sẵn sàng khi tải thực tế vượt ngưỡng CPU/connection của 1 instance.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. Không bao giờ đánh giá hiệu năng chỉ bằng latency trung bình — phải đo **p95/p99** và kiểm tra bằng SLO tự động để phát hiện tail latency.
  2. Benchmark chất lượng (**eval trên golden dataset**) và chỉ số **cost / câu đúng** là bắt buộc song song với load test, vì metrics hạ tầng không thể phát hiện suy giảm chất lượng trả lời (như khi rollback nhầm về v1).
  3. Sự kết nối 3 trụ cột **Metrics (Prometheus/Grafana) → Traces (OpenTelemetry/Jaeger) → Structured JSON Logs (`trace_id`)** giúp thu hẹp nguyên nhân gốc rễ (như biết ngay 95.7% thời gian nằm ở span gọi LLM) chỉ trong vài giây.
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert:**
  - Metric & alert cho **Redis latency / connection errors** và tỉ lệ **429 (rate limit) / 402 (budget exceeded)** để phát hiện lạm dụng hoặc hết hạn mức.
  - **TTFT (Time To First Token)** nếu dùng streaming LLM, và **eval quality score** định kỳ để cảnh báo drift/hallucination.
