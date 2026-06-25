# Minimal worker placeholder to satisfy docker-compose
import asyncio

async def main():
    print("Worker starting...")
    while True:
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
