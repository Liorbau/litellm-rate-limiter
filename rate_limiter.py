import asyncio
import math
import os
import requests
import time

from openai import APIConnectionError, AsyncOpenAI

BASE_URL = "http://localhost:4000"
MODEL_INFO_ENDPOINT = f"{BASE_URL}/v1/model/info"
MODEL_ALIAS = "my-model"

MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY")
if not MASTER_KEY:
    raise RuntimeError(
        "Set LITELLM_MASTER_KEY to the LiteLLM proxy master key (same as in your environment when starting the proxy)."
    )

client = AsyncOpenAI(
    api_key=MASTER_KEY,
    base_url=BASE_URL,
)


#====================== step 1 ======================
def get_rpm() -> int:  
    """
    Returns the RPM limit for the model (all deployments)
    """
    headers = {"Authorization": f"Bearer {MASTER_KEY}"}

    try:
        response = requests.get(MODEL_INFO_ENDPOINT, headers=headers)
    except requests.ConnectionError:
        raise RuntimeError(f"Cannot reach LiteLLM proxy at {BASE_URL}.")

    if response.status_code != 200:
        raise RuntimeError(f"Failed to get model info: {response.status_code} {response.text}")

    data = response.json()["data"]

    total_rpm = 0
    found = False

    for deployment in data:
        if deployment["model_name"] == MODEL_ALIAS:
            found = True
            rpm = deployment["litellm_params"].get("rpm")

            if rpm is not None:
                total_rpm += int(rpm)

    if not found:
        raise ValueError(f"Model '{MODEL_ALIAS}' not found in /model/info")

    if total_rpm <= 0:
        raise ValueError(f"Invalid or missing RPM = {total_rpm} for {MODEL_ALIAS}")

    return total_rpm


#====================== step 2 ======================
async def measure_completion_time(num_requests: int = 5) -> float: 
    """
    Sends warm-up requests to the LLM to calculate the average latency.
    """
    total_time = 0
    successes = 0

    for i in range(num_requests):
        try:
            start_time = time.perf_counter()
            
            response = await client.chat.completions.create(
                model=MODEL_ALIAS,
                messages=[{"role": "user", "content": f"Count to 5, then append this once: {i}"}],
            )

            end_time = time.perf_counter()
            response_time = end_time - start_time
            total_time += response_time
            successes += 1

        except APIConnectionError as e:
            print(f"  Request {i+1}: FAILED - {e}")

    if successes == 0:
        raise RuntimeError("No successful requests were made.")

    return total_time / successes


#====================== step 3 ======================
def calculate_pacing(rpm: int, avg_completion_time: float) -> tuple:   
    """
    Calculates the optimal pacing for the LLM API.
    """
    max_rps = rpm / 60
    single_worker_rps = 1 / avg_completion_time
    expected_concurrency = math.ceil(max_rps / single_worker_rps)
    return max_rps, single_worker_rps, expected_concurrency


#====================== step 4 ======================
async def worker(request_num: int, sem: asyncio.Semaphore, live_stats: dict) -> bool:
    """Sends a single request to the proxy and returns True if successful."""
    try:
        async with sem:
            response = await client.chat.completions.create(
                model=MODEL_ALIAS,
                messages=[{"role": "user", "content": f"Count to 5, then append this once: {request_num}"}]
            )
        live_stats["success"] += 1
        return True
    except Exception as e:
        print(f"  Request {request_num}: FAILED - {e}")
        live_stats["failed"] += 1
        return False


async def run_workload(total_requests: int, expected_concurrency: int, target_time: int = 60) -> tuple:
    """
    Runs the workload and returns the results and total time.
    """
    if total_requests <= 0:
        raise ValueError("total_requests must be positive")

    sem = asyncio.Semaphore(expected_concurrency)
    live_stats = {"sent": 0, "success": 0, "failed": 0}
    milestones = (1, 10, 30, 60)
    milestone_index = 0
    sleep_time = target_time / total_requests
    tasks = []
    start_time = time.perf_counter()

    print(f"\nSending {total_requests} requests...")

    for i in range(total_requests):
        task = asyncio.create_task(worker(i + 1, sem, live_stats))
        tasks.append(task)
        live_stats["sent"] += 1
        await asyncio.sleep(sleep_time)
        elapsed = time.perf_counter() - start_time
        while milestone_index < len(milestones) and elapsed >= milestones[milestone_index]:
            m = milestones[milestone_index]
            # [00:60] printed after gather.
            if m == 60:
                break
            print(
                f"[00:{m:02d}] Sent {live_stats['sent']}, Success {live_stats['success']}, Failed {live_stats['failed']}"
            )
            milestone_index += 1

    results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start_time
    # Collects any deferred milestones
    while milestone_index < len(milestones) and elapsed >= milestones[milestone_index]:
        m = milestones[milestone_index]
        print(
            f"[00:{m:02d}] Sent {live_stats['sent']}, Success {live_stats['success']}, Failed {live_stats['failed']}"
        )
        milestone_index += 1
    end_time = time.perf_counter()
    total_time = end_time - start_time
    success = sum(1 for r in results if r is True)

    return success, total_time


#=====================================================
async def main():
    rpm = get_rpm() 
    print(f"\nInit:\nDiscovered RPM limit: {rpm}")

    num_requests = 5    # Or other
    avg_time = await measure_completion_time(num_requests)
    print(f"Average completion time: {avg_time:.2f}s")

    max_rps, _, expected_concurrency = calculate_pacing(rpm, avg_time)
    print(f"Expected number of requests to be sent: {max_rps:.2f} requests/sec")
    print(f"Expected Concurrency: {expected_concurrency}")

    # Warm-up + workload must not exceed RPM in a rolling minute.
    total_requests = rpm - num_requests
    if total_requests <= 0:
        raise ValueError(f"RPM ({rpm}) must be greater than warm-up count ({num_requests}).")
    success, total_time = await run_workload(total_requests, expected_concurrency)

    failed = total_requests - success
    print(f"\n=== Summary ===")
    print(f"Total requests: {total_requests}")
    print(f"Successful: {success} ({success / total_requests * 100:.0f}%)")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Actual RPS: {success / total_time:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
