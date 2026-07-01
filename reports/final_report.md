# Day 10 Reliability Report

## 1. Architecture summary

The gateway processes each request in the order cache -> circuit breaker -> provider chain -> static fallback. The design goal is to reduce cost with semantic caching, prevent retry storms with circuit breakers, and still return a response when the primary provider fails.

```text
User Request
    |
    v
[ReliabilityGateway]
    |
    +--> [ResponseCache / SharedRedisCache] -- hit --> return cached response
    |
    v miss
[Circuit Breaker: primary] -- closed/half-open --> [Provider primary]
    |                                  |
    | open / provider error            v success
    |------------------------------> cache set + return
    v
[Circuit Breaker: backup] -- closed/half-open --> [Provider backup]
    |                                  |
    | open / provider error            v success
    |------------------------------> cache set + return fallback
    v
[Static fallback message]
```

## 2. Configuration

| Setting | Value | Reason |
|---|---:|---|
| failure_threshold | 3 | Open the circuit after 3 consecutive failures to stop retry storms without being too sensitive to random noise. |
| reset_timeout_seconds | 2 | Give the provider a short recovery window before allowing a probe request. |
| success_threshold | 1 | One successful probe is enough to close the circuit again for this lab workload. |
| cache TTL | 300 | Long enough for repeated sample queries, short enough to avoid long-lived stale content. |
| similarity_threshold | 0.92 | High threshold to reduce semantic false hits, especially for queries containing years or numeric identifiers. |
| load_test requests | 100 per scenario | Enough volume to expose hit rate, circuit transitions, and latency percentiles. |

## 3. SLO definitions

| SLI | SLO target | Actual value | Met? |
|---|---|---:|---|
| Availability | >= 99% | 98.00% | No |
| Latency P95 | < 2500 ms | 497.76 ms | Yes |
| Fallback success rate | >= 95% | 92.21% | No |
| Cache hit rate | >= 10% | 61.67% | Yes |
| Recovery time | < 5000 ms | 2508.78 ms | Yes |

## 4. Metrics

Source data: [metrics.json](/E:/AITHUCCHIEN/LAB/2A202600809-LeVuAnh-Day25/reports/metrics.json)

| Metric | Value |
|---|---:|
| availability | 0.9800 |
| error_rate | 0.0200 |
| latency_p50_ms | 0.85 |
| latency_p95_ms | 497.76 |
| latency_p99_ms | 541.55 |
| fallback_success_rate | 0.9221 |
| cache_hit_rate | 0.6167 |
| estimated_cost_saved | 0.185 |
| circuit_open_count | 8 |
| recovery_time_ms | 2508.78 |

## 5. Cache comparison

This compares the current memory-cache baseline against a run with cache disabled:

| Metric | Without cache | With cache | Delta |
|---|---:|---:|---|
| latency_p50_ms | 283.84 | 0.85 | -282.99 ms |
| latency_p95_ms | 526.12 | 497.76 | -28.36 ms |
| estimated_cost | 0.122914 | 0.047580 | -0.075334 |
| cache_hit_rate | 0.0000 | 0.6167 | +0.6167 |

Observation: after switching to end-to-end latency measurement, memory cache is clearly faster at P50 and modestly faster at P95 while also cutting estimated cost by about 61%.

## 6. Redis shared cache

- In-memory cache is not enough for multi-instance deployment because each instance keeps its own state; warming one instance does not help the others.
- `SharedRedisCache` moves cache state into Redis so every gateway instance reads and writes the same shared namespace, with TTL cleanup handled by Redis.

### Evidence of shared state

Two separate cache instances can read the same entry:

```text
('shared response demo', 1.0)
```

### Redis CLI output

```bash
$ docker compose exec redis redis-cli KEYS "rl:cache:*"
rl:cache:fff10da1c72c
rl:cache:3dab98c0e49e
rl:cache:b2a52f7dc795
rl:cache:734852f3cf4a
rl:cache:844ef0143a5c
rl:cache:095946136fea
rl:cache:8baa2cfa11fa
rl:cache:d354658dc020
rl:cache:0bc3b1acf73d
rl:cache:dacb2b833659
rl:cache:9e413fd814eb
rl:cache:da61fb49b4f6
rl:cache:98332d0d1c9c
```

### In-memory vs Redis latency comparison

| Metric | In-memory cache | Redis cache | Notes |
|---|---:|---:|---|
| latency_p50_ms | 0.85 | 1.07 | Both are effectively cache-hit speed; Redis adds slight network overhead but stays near 1 ms at P50. |
| latency_p95_ms | 497.76 | 461.35 | Redis run was slightly better in this sample because of a higher hit rate and lower fallback pressure. |

## 7. Chaos scenarios

| Scenario | Expected behavior | Observed behavior | Pass/Fail |
|---|---|---|---|
| primary_timeout_100 | All traffic fallback to backup, circuit opens | Availability 99.0%, fallback success rate 97.22%, cache hit rate 64%, circuit opened 5 times. Static fallback only appeared when backup also failed. | Pass |
| primary_flaky_50 | Circuit oscillates, mix of primary and fallback | Availability 100%, fallback success rate 100%, cache hit rate 57%, circuit opened 1 time. This run did not produce a full open-to-close recovery pair. | Pass |
| all_healthy | All requests via primary, no circuit opens | Availability 99%, P95 295.42 ms, cache hit rate 58%, circuit_open_count 0. The lower fallback success rate here comes from very few fallback attempts, so one miss moves the ratio sharply. | Pass |
| redis_backend_smoke | Shared cache works across instances and chaos run still succeeds | Redis run reached 98.67% availability, P50 1.07 ms, P95 461.35 ms, 71.33% cache hit rate, estimated cost 0.034388, and Redis stored shared keys. | Pass |

## 8. Failure analysis

The main remaining weakness is that circuit breaker state is still local to each process. In a multi-instance deployment, one instance may open its circuit while another instance keeps sending traffic to the same failing provider.

Before production, I would move breaker counters and state into Redis with `INCR`, `EXPIRE`, and a dedicated `opened_at` key so all instances share the same provider health view. I would also tighten the fallback policy and run larger load tests, because the current real run still missed the 99% availability and 95% fallback-success SLOs even though latency improved materially once cache hits were measured correctly.

## 9. Next steps

1. Share circuit breaker state through Redis to avoid split-brain between gateway instances.
2. Promote cache/no-cache and memory/redis comparisons into first-class scenarios in `run_simulation`.
3. Add quality SLOs for cache hits, for example auditing false-hit rate for queries with years or sensitive patterns.
