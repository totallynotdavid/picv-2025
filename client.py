import asyncio
import json
import time
from datetime import datetime

import aiohttp


async def test_tsdhn_api():
    # Test data
    earthquake_data = {
        "Mw": 9.0,
        "h": 12,
        "lat0": 56,
        "lon0": -156,
        "hhmm": "0000",
        "dia": "23",
    }

    # API base URL
    base_url = "http://localhost:8000"

    async with aiohttp.ClientSession() as session:
        try:
            print("\n=== Starting TSDHN API Test ===")
            print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("\nInput parameters:")
            print(json.dumps(earthquake_data, indent=2))

            # Test /calculate endpoint
            print("\n1. Testing /calculate endpoint...")
            async with session.post(
                f"{base_url}/calculate", json=earthquake_data
            ) as response:
                calculate_result = await response.json()
                print(f"Status: {response.status}")
                print("Response:")
                print(json.dumps(calculate_result, indent=2))

            # Test /tsunami-travel-times endpoint
            print("\n2. Testing /tsunami-travel-times endpoint...")
            async with session.post(
                f"{base_url}/tsunami-travel-times", json=earthquake_data
            ) as response:
                travel_times = await response.json()
                print(f"Status: {response.status}")
                print("Response:")
                print(json.dumps(travel_times, indent=2))

            # Test /run-tsdhn endpoint and job status
            print("\n3. Testing /run-tsdhn endpoint and job monitoring...")
            async with session.post(f"{base_url}/run-tsdhn") as response:
                tsdhn_response = await response.json()
                job_id = tsdhn_response["job_id"]
                print(f"Job ID: {job_id}")
                print("Initial response:")
                print(json.dumps(tsdhn_response, indent=2))

                # Monitor job status for 1 minute
                print("\nMonitoring job status (for 60 seconds)...")
                start_time = time.time()
                while time.time() - start_time < 60:
                    async with session.get(
                        f"{base_url}/job-status/{job_id}"
                    ) as status_response:
                        status = await status_response.json()
                        print(
                            f"\nStatus check at {datetime.now().strftime('%H:%M:%S')}:"
                        )
                        print(json.dumps(status, indent=2))

                        if status["status"] == "completed":
                            print("\nJob completed! Attempting to fetch results...")
                            async with session.get(
                                f"{base_url}/job-result/{job_id}"
                            ) as result_response:
                                if result_response.status == 200:
                                    # Save the PDF
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

                    await asyncio.sleep(5)  # Wait 5 seconds between checks

                print("\nTest completed!")

        except Exception as e:
            print(f"\nError during test: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_tsdhn_api())
