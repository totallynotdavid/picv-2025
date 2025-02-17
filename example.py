import argparse
import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp


async def test_endpoints(base_url="http://localhost:8000"):
    # Change these parameters to test different scenarios
    earthquake_data = {
        "Mw": 9.0,
        "h": 12,
        "lat0": 56,
        "lon0": -156,
        "hhmm": "0000",
        "dia": "23",
    }

    async with aiohttp.ClientSession() as session:
        try:
            print(
                "\n=== Starting TSDHN API Test at",
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===",
            )
            print(f"Input parameters:\n{json.dumps(earthquake_data, indent=2)}")

            # Test /calculate endpoint
            print("\n1. Testing /calculate endpoint...")
            async with session.post(
                f"{base_url}/calculate", json=earthquake_data
            ) as response:
                print(f"Status: {response.status}\nResponse:")
                print(json.dumps(await response.json(), indent=2))

            # Test /tsunami-travel-times endpoint
            print("\n2. Testing /tsunami-travel-times endpoint...")
            async with session.post(
                f"{base_url}/tsunami-travel-times", json=earthquake_data
            ) as response:
                print(f"Status: {response.status}\nResponse:")
                print(json.dumps(await response.json(), indent=2))

            # Submit job
            print("\n3. Testing /run-tsdhn endpoint submission...")
            async with session.post(f"{base_url}/run-tsdhn") as response:
                response_data = await response.json()
                job_id = response_data["job_id"]
                print(f"Job ID: {job_id}\nInitial response:")
                print(json.dumps(response_data, indent=2))

                # Save job ID to file
                with open("last_job_id.txt", "w") as f:
                    f.write(job_id)
                print("Job ID saved to last_job_id.txt")

            return job_id

        except Exception as e:
            print(f"\nError during endpoint testing: {str(e)}")
            return None


async def monitor_job(
    job_id,
    base_url="http://localhost:8000",
    check_interval=60,
    timeout=None,
    save_result=True,
):
    """Monitor a previously submitted job"""
    if not job_id:
        print("No job ID provided. Please specify a job ID to monitor.")
        return

    print(f"\n=== Monitoring TSDHN Job: {job_id} ===")
    print(f"Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(
        f"Checking status every {check_interval} seconds"
        + (f", timeout after {timeout / 60:.1f} minutes" if timeout else "")
    )

    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        while True:
            # Check timeout
            if timeout and (time.time() - start_time > timeout):
                print(f"\nTimeout reached after {timeout / 60:.1f} minutes.")
                print(
                    "Resume monitoring with:",
                    f"python {os.path.basename(__file__)} --monitor {job_id}",
                )
                break

            try:
                async with session.get(
                    f"{base_url}/job-status/{job_id}"
                ) as status_response:
                    status = await status_response.json()
                    elapsed_minutes = (time.time() - start_time) / 60

                    print(
                        f"\nStatus check at {datetime.now().strftime('%H:%M:%S')} "
                        + f"(elapsed: {elapsed_minutes:.1f} min):"
                    )
                    print(json.dumps(status, indent=2))

                    if status["status"] == "completed":
                        print("\nJob completed! Fetching results...")
                        if save_result:
                            async with session.get(
                                f"{base_url}/job-result/{job_id}"
                            ) as result_response:
                                if result_response.status == 200:
                                    filename = f"tsdhn_report_{job_id}.pdf"
                                    with open(filename, "wb") as f:
                                        f.write(await result_response.read())
                                    print(f"Report saved as: {filename}")
                                else:
                                    print(
                                        "Error fetching results:",
                                        f"{await result_response.text()}",
                                    )
                        break
                    elif status["status"] == "failed":
                        print("Job failed!")
                        break

                    print(f"Waiting {check_interval} seconds before next check...")

            except Exception as e:
                print(f"Error checking status: {str(e)}")

            # Wait before next check
            await asyncio.sleep(check_interval)


async def main():
    parser = argparse.ArgumentParser(description="TSDHN API Testing Tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true", help="Run tests on all endpoints")
    group.add_argument(
        "--monitor",
        metavar="JOB_ID",
        help='Monitor an existing job (use "last" for most recent)',
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--timeout", type=int, help="Maximum monitoring time in seconds (optional)"
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Do not save result files"
    )

    args = parser.parse_args()

    if args.test:
        job_id = await test_endpoints(args.url)
        if job_id and input("\nStart monitoring this job? (y/n): ").lower() == "y":
            await monitor_job(
                job_id, args.url, args.interval, args.timeout, not args.no_save
            )
    else:  # args.monitor must be present due to mutually exclusive group
        job_id = args.monitor
        if job_id == "last":
            try:
                with open("last_job_id.txt", "r") as f:
                    job_id = f.read().strip()
                    print(f"Using last job ID: {job_id}")
            except FileNotFoundError:
                print("No last job ID found. Please provide a specific job ID.")
                return
        await monitor_job(
            job_id, args.url, args.interval, args.timeout, not args.no_save
        )


if __name__ == "__main__":
    asyncio.run(main())
