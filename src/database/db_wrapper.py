"""
Secure Database Wrapper for Clinic Assistant Chatbot
- No direct LLM access to database
- Parameterized queries only (SQL injection protected)
- Connection pooling for high concurrency
- Redis caching for performance
"""
import logging
import hashlib
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import asyncio

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_config

logger = logging.getLogger(__name__)


class DBWrapper:
    """
    Secure Database Access Layer
    - Isolates database from LLM
    - Uses ONLY parameterized queries
    - Implements caching for performance
    """
    
    def __init__(self):
        self.config = get_config()
        self.pool: Optional[Any] = None
        self.redis: Optional[Any] = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize database connection pool and Redis cache"""
        try:
            if ASYNCPG_AVAILABLE:
                self.pool = await asyncpg.create_pool(
                    host=self.config.postgres.host,
                    port=self.config.postgres.port,
                    database=self.config.postgres.database,
                    user=self.config.postgres.user,
                    password=self.config.postgres.password,
                    min_size=self.config.postgres.min_connections,
                    max_size=self.config.postgres.max_connections
                )
                logger.info("PostgreSQL connection pool initialized")
            else:
                logger.warning("asyncpg not available - using in-memory fallback")
            
            if REDIS_AVAILABLE and self.config.redis.host:
                self.redis = await aioredis.from_url(
                    self.config.redis.connection_url,
                    decode_responses=True
                )
                logger.info("Redis cache initialized")
            else:
                logger.warning("Redis not available - caching disabled")
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    async def close(self):
        """Close all connections"""
        if self.pool:
            await self.pool.close()
        if self.redis:
            await self.redis.close()
    
    def _cache_key(self, prefix: str, query: str, params: tuple) -> str:
        """Generate cache key from query and parameters"""
        data = f"{query}:{json.dumps(params, default=str)}"
        return f"{prefix}:{hashlib.md5(data.encode()).hexdigest()}"
    
    async def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if self.redis:
            try:
                data = await self.redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Cache get failed: {e}")
        return None
    
    async def _set_cached(self, key: str, value: Any, ttl: int = None):
        """Set value in cache"""
        if self.redis:
            try:
                ttl = ttl or self.config.redis.ttl
                await self.redis.setex(key, ttl, json.dumps(value, default=str))
            except Exception as e:
                logger.warning(f"Cache set failed: {e}")
    
    # ========================================
    # FAQ QUERIES - Main chatbot interface
    # ========================================
    
    async def search_faq(self, keywords: List[str], lang: str = 'en') -> Optional[Dict]:
        """
        Search FAQs by keywords
        PARAMETERIZED QUERY - SQL injection safe
        """
        logger.info(f"search_faq called with keywords={keywords}, lang={lang}, pool={self.pool is not None}")
        
        cache_key = self._cache_key("faq", "search", tuple(keywords))
        cached = await self._get_cached(cache_key)
        if cached:
            logger.info("Returning cached FAQ result")
            return cached
        
        if not self.pool:
            logger.warning("No database pool - using fallback")
            return self._fallback_faq_search(keywords, lang)
        
        try:
            # Search by question or answer text matching keywords
            query = """
                SELECT faq_id, question, answer, 
                       COALESCE(answer_hi, answer) as answer_hi, 
                       COALESCE(answer_te, answer) as answer_te, 
                       COALESCE(category, 'general') as category
                FROM faqs
                WHERE LOWER(question) LIKE ANY($1::text[])
                   OR LOWER(answer) LIKE ANY($1::text[])
                LIMIT 1
            """
            # Create LIKE patterns from keywords
            like_patterns = [f'%{kw.lower()}%' for kw in keywords]
            
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, like_patterns)
                logger.info(f"FAQ query result: {row is not None}")
                
                if row:
                    # Select language-appropriate answer
                    if lang == 'hi' and row['answer_hi']:
                        answer = row['answer_hi']
                    elif lang == 'te' and row['answer_te']:
                        answer = row['answer_te']
                    else:
                        answer = row['answer']
                    
                    result = {
                        'faq_id': row['faq_id'],
                        'question': row['question'],
                        'answer': answer,
                        'category': row['category'],
                        'matched_keywords': keywords  # Return the search keywords
                    }
                    
                    await self._set_cached(cache_key, result)
                    
                    # Update hit count (fire and forget) - skip if column doesn't exist
                    try:
                        asyncio.create_task(self._increment_faq_hit(row['faq_id']))
                    except Exception:
                        pass
                    
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"FAQ search failed: {e}")
            return self._fallback_faq_search(keywords, lang)
    
    async def _increment_faq_hit(self, faq_id: int):
        """Increment FAQ hit count for analytics (if column exists)"""
        if not self.pool:
            return
        try:
            # Try to update hit_count - silently fail if column doesn't exist
            query = "UPDATE faqs SET hit_count = COALESCE(hit_count, 0) + 1 WHERE faq_id = $1"
            async with self.pool.acquire() as conn:
                await conn.execute(query, faq_id)
        except Exception as e:
            # Silently ignore - hit_count column may not exist
            pass
    
    def _fallback_faq_search(self, keywords: List[str], lang: str) -> Optional[Dict]:
        """Fallback FAQ search using in-memory data"""
        # In-memory FAQ data for when database is unavailable
        FALLBACK_FAQS = {
            'cardiology': {
                'en': 'Cardiology OPD is in the Super Speciality Block, Room No. 106. OPD timings: 9 AM to 1 PM, Monday to Saturday.',
                'hi': 'कार्डियोलॉजी ओपीडी सुपर स्पेशियलिटी ब्लॉक में है, कमरा नंबर 106। ओपीडी समय: सुबह 9 बजे से दोपहर 1 बजे तक, सोमवार से शनिवार।',
                'te': 'కార్డియాలజీ OPD సూపర్ స్పెషాలిటీ బ్లాక్‌లో ఉంది, రూమ్ నంబర్ 106. OPD సమయాలు: ఉదయం 9 నుండి మధ్యాహ్నం 1 వరకు, సోమవారం నుండి శనివారం వరకు.'
            },
            'emergency': {
                'en': 'The emergency ward is located on the ground floor, near the Trauma Care Unit. Available 24/7.',
                'hi': 'आपातकालीन वार्ड भूतल पर, ट्रॉमा केयर यूनिट के पास स्थित है। 24/7 उपलब्ध।',
                'te': 'ఎమర్జెన్సీ వార్డు గ్రౌండ్ ఫ్లోర్‌లో, ట్రామా కేర్ యూనిట్ సమీపంలో ఉంది. 24/7 అందుబాటులో ఉంది.'
            },
            'pharmacy': {
                'en': 'Pharmacy (Balaji Medical Shop) is opposite to Admin Block. Open 24/7.',
                'hi': 'फार्मेसी (बालाजी मेडिकल शॉप) एडमिन ब्लॉक के सामने है। 24/7 खुला।',
                'te': 'ఫార్మసీ (బాలాజీ మెడికల్ షాప్) అడ్మిన్ బ్లాక్ ఎదురుగా ఉంది. 24/7 తెరిచి ఉంటుంది.'
            },
            'admission': {
                'en': 'Admission counter is on the ground floor, near the OP registration desk. Required: Doctor\'s referral and ID proof.',
                'hi': 'एडमिशन काउंटर भूतल पर है, ओपी रजिस्ट्रेशन डेस्क के पास। आवश्यक: डॉक्टर का रेफरल और आईडी प्रूफ।',
                'te': 'అడ్మిషన్ కౌంటర్ గ్రౌండ్ ఫ్లోర్‌లో ఉంది, OP రిజిస్ట్రేషన్ డెస్క్ సమీపంలో. అవసరం: డాక్టర్ రెఫరల్ మరియు ID ప్రూఫ్.'
            },
            'aarogyasri': {
                'en': 'Yes, Aarogyasri scheme is supported. Register at the Aarogyasri help desk, ground floor. Required: Aarogyasri card, Aadhaar, doctor\'s referral.',
                'hi': 'हां, आरोग्यश्री योजना समर्थित है। आरोग्यश्री हेल्प डेस्क पर रजिस्टर करें, भूतल पर। आवश्यक: आरोग्यश्री कार्ड, आधार, डॉक्टर का रेफरल।',
                'te': 'అవును, ఆరోగ్యశ్రీ పథకం అందుబాటులో ఉంది. ఆరోగ్యశ్రీ హెల్ప్ డెస్క్ వద్ద రిజిస్టర్ చేసుకోండి, గ్రౌండ్ ఫ్లోర్‌లో. అవసరం: ఆరోగ్యశ్రీ కార్డ్, ఆధార్, డాక్టర్ రెఫరల్.'
            }
        }
        
        keywords_lower = [k.lower() for k in keywords]
        
        for key, responses in FALLBACK_FAQS.items():
            if key in keywords_lower or any(key in kw for kw in keywords_lower):
                return {
                    'faq_id': 0,
                    'question': f'About {key}',
                    'answer': responses.get(lang, responses['en']),
                    'category': key,
                    'matched_keywords': [key],
                    'source': 'fallback'
                }
        
        return None
    
    # ========================================
    # DEPARTMENT QUERIES
    # ========================================
    
    async def get_department_info(self, keywords: List[str], lang: str = 'en') -> Optional[Dict]:
        """
        Get department information by keywords
        PARAMETERIZED QUERY - SQL injection safe
        """
        if not self.pool:
            return None
        
        try:
            # Search by department_name matching any keyword
            query = """
                SELECT department_id, department_name, location, block, floor, 
                       room_number, head_doctor, opd_timings, contact_number, services
                FROM departments
                WHERE LOWER(department_name) LIKE ANY($1::text[])
                LIMIT 1
            """
            # Create LIKE patterns from keywords
            like_patterns = [f'%{kw.lower()}%' for kw in keywords]
            
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, like_patterns)
                
                if row:
                    location_parts = []
                    if row['block']:
                        location_parts.append(row['block'])
                    if row['floor']:
                        location_parts.append(row['floor'])
                    if row.get('room_number'):
                        location_parts.append(f"Room {row['room_number']}")
                    
                    return {
                        'department_id': row['department_id'],
                        'name': row['department_name'],
                        'location': row['location'] or ', '.join(location_parts),
                        'head_doctor': row.get('head_doctor', ''),
                        'timings': row.get('opd_timings', ''),
                        'contact': row.get('contact_number', ''),
                        'services': row.get('services', '')
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Department query failed: {e}")
            return None
    
    # ========================================
    # FACILITY QUERIES
    # ========================================
    
    async def get_facility_info(self, keywords: List[str]) -> Optional[Dict]:
        """
        Get facility information by keywords
        PARAMETERIZED QUERY - SQL injection safe
        """
        if not self.pool:
            return None
        
        try:
            # Search by facility_name or facility_type matching any keyword
            query = """
                SELECT facility_id, facility_name, facility_type, location, block, floor, 
                       timings, contact_number, description
                FROM facilities
                WHERE LOWER(facility_name) LIKE ANY($1::text[])
                   OR LOWER(facility_type) LIKE ANY($1::text[])
                LIMIT 1
            """
            # Create LIKE patterns from keywords
            like_patterns = [f'%{kw.lower()}%' for kw in keywords]
            
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, like_patterns)
                
                if row:
                    return {
                        'facility_id': row['facility_id'],
                        'name': row['facility_name'],
                        'type': row['facility_type'],
                        'location': row['location'] or f"{row['block']}, {row['floor']}",
                        'timings': row['timings'],
                        'contact': row.get('contact_number', ''),
                        'description': row.get('description', '')
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Facility query failed: {e}")
            return None
    
    # ========================================
    # CONVERSATION LOGGING
    # ========================================
    
    async def log_conversation(
        self,
        session_id: str,
        user_input: str,
        detected_language: str,
        intent: str,
        matched_faq_id: Optional[int],
        bot_response: str,
        response_language: str,
        confidence_score: float,
        response_time_ms: int
    ):
        """
        Log conversation for audit trail
        PARAMETERIZED QUERY - SQL injection safe
        """
        if not self.pool:
            logger.info(f"Conversation log (no DB): session={session_id}, intent={intent}")
            return
        
        try:
            query = """
                INSERT INTO conversation_logs 
                (session_id, user_input, detected_language, intent, matched_faq_id,
                 bot_response, response_language, confidence_score, response_time_ms)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
            """
            
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    session_id,
                    user_input,
                    detected_language,
                    intent,
                    matched_faq_id,
                    bot_response,
                    response_language,
                    confidence_score,
                    response_time_ms
                )
                
        except Exception as e:
            logger.error(f"Conversation logging failed: {e}")
    
    # ========================================
    # HEALTH CHECK
    # ========================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database and cache health"""
        status = {
            'database': 'unknown',
            'cache': 'unknown',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Check database
        if self.pool:
            try:
                async with self.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                status['database'] = 'healthy'
            except Exception as e:
                status['database'] = f'unhealthy: {str(e)}'
        else:
            status['database'] = 'not_configured'
        
        # Check Redis
        if self.redis:
            try:
                await self.redis.ping()
                status['cache'] = 'healthy'
            except Exception as e:
                status['cache'] = f'unhealthy: {str(e)}'
        else:
            status['cache'] = 'not_configured'
        
        return status


# Global instance
_db_wrapper: Optional[DBWrapper] = None


async def get_db_wrapper() -> DBWrapper:
    """Get or create the global DBWrapper instance"""
    global _db_wrapper
    if _db_wrapper is None:
        _db_wrapper = DBWrapper()
        await _db_wrapper.initialize()
    return _db_wrapper


# ========================================
# STANDALONE TEST
# ========================================
if __name__ == "__main__":
    async def test():
        db = DBWrapper()
        
        # Test fallback search (no DB connection needed)
        result = db._fallback_faq_search(['cardiology', 'heart'], 'te')
        print(f"Fallback search result: {result}")
        
        result = db._fallback_faq_search(['emergency'], 'hi')
        print(f"Emergency fallback: {result}")
    
    asyncio.run(test())
