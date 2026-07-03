import asyncio
from uuid import uuid4
from backend.db.pool import create_pool, get_pool
from pipelines.finetuning.extractor import FineTuneExtractor

async def main():
    await create_pool()
    pool = get_pool()
    
    extractor = FineTuneExtractor(pool, None)
    
    # 1. Test PII
    pair_pii = {
        "user_message": "My email is test@example.com",
        "assistant_message": "Here is a 50 token response " + "word "*45 + "[Source 1]",
    }
    # 2. Test short response
    pair_short = {
        "user_message": "What is NeuroFlow?",
        "assistant_message": "Too short [Source 1]",
    }
    
    valid_pii = await extractor.validate_pair(pair_pii)
    valid_short = await extractor.validate_pair(pair_short)
    
    print('PII valid:', valid_pii)
    print('Short valid:', valid_short)
    
    assert not valid_pii, "PII should be rejected"
    assert not valid_short, "Short should be rejected"
    print("JSONL validation PASSED")

if __name__ == "__main__":
    asyncio.run(main())
