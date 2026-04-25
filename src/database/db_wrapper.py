"""
Secure Database Wrapper for NIMS Hospital Voice Assistant
---------------------------------------------------------
Queries all 6 tables in the existing nims_hospital_db:
  departments, doctors, wards, nurses, appointments, hospital_info

- No direct LLM access to database
- Parameterized queries only (SQL injection safe)
- Connection pooling via asyncpg
- Redis caching (optional, graceful degradation)
"""
import logging
import hashlib
import json
from typing import Optional, List, Dict, Any
from datetime import date, datetime
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
    Secure Database Access Layer — covers all 6 tables.

    Tables queried:
      departments   – hospital departments (name, floor, room, phone)
      doctors       – physicians (name, specialization, availability, schedule)
      wards         – ward beds (type, available_beds)
      nurses        – nursing staff (name, department, ward, shift)
      appointments  – patient bookings
      hospital_info – key-value pairs (visiting hours, pharmacy, etc.)
    """

    def __init__(self):
        self.config = get_config()
        self.pool: Optional[Any] = None
        self.redis: Optional[Any] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize database connection pool and optional Redis cache."""
        try:
            if ASYNCPG_AVAILABLE:
                self.pool = await asyncpg.create_pool(
                    host=self.config.postgres.host,
                    port=self.config.postgres.port,
                    database=self.config.postgres.database,
                    user=self.config.postgres.user,
                    password=self.config.postgres.password,
                    min_size=1,
                    max_size=5,
                )
                logger.info("PostgreSQL connection pool initialized")
            else:
                logger.warning("asyncpg not available — DB queries will fail")

            if REDIS_AVAILABLE and self.config.redis.host:
                try:
                    self.redis = await aioredis.from_url(
                        self.config.redis.connection_url,
                        decode_responses=True,
                    )
                    logger.info("Redis cache initialized")
                except Exception:
                    logger.warning("Redis not available — caching disabled")

            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False

    async def close(self):
        if self.pool:
            await self.pool.close()
        if self.redis:
            await self.redis.close()

    # ── Cache helpers ────────────────────────────────────────────────────

    def _cache_key(self, prefix: str, *parts) -> str:
        data = json.dumps(parts, default=str)
        return f"{prefix}:{hashlib.md5(data.encode()).hexdigest()}"

    async def _get_cached(self, key: str) -> Optional[Any]:
        if self.redis:
            try:
                data = await self.redis.get(key)
                if data:
                    return json.loads(data)
            except Exception:
                pass
        return None

    async def _set_cached(self, key: str, value: Any, ttl: int = 3600):
        if self.redis:
            try:
                await self.redis.setex(key, ttl, json.dumps(value, default=str))
            except Exception:
                pass

    # ====================================================================
    # DOCTORS
    # ====================================================================

    async def find_doctors_by_keyword(self, keyword: str) -> List[Dict]:
        """Search doctors by name (partial match)."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT d.doctor_id, d.name, d.specialization, d.qualification,
                       d.department_id, dep.name AS dept_name,
                       d.registration_number, d.floor, d.room_no,
                       d.availability, d.available_days, d.available_time,
                       d.consultation_fee, d.phone_ext, d.is_active
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.department_id
                WHERE LOWER(d.name) LIKE $1 AND d.is_active = TRUE
                LIMIT 5
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, f"%{keyword.lower()}%")
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_doctors_by_keyword failed: {e}")
            return []

    async def find_doctors_by_specialization(self, spec: str) -> List[Dict]:
        """Search doctors by specialization keyword."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT d.doctor_id, d.name, d.specialization, d.qualification,
                       d.department_id, dep.name AS dept_name,
                       d.registration_number, d.floor, d.room_no,
                       d.availability, d.available_days, d.available_time,
                       d.consultation_fee, d.phone_ext, d.is_active
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.department_id
                WHERE LOWER(d.specialization) LIKE $1 AND d.is_active = TRUE
                LIMIT 5
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, f"%{spec.lower()}%")
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_doctors_by_specialization failed: {e}")
            return []

    async def find_doctors_by_department(self, dept_name: str) -> List[Dict]:
        """Search doctors by department name."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT d.doctor_id, d.name, d.specialization, d.qualification,
                       d.department_id, dep.name AS dept_name,
                       d.registration_number, d.floor, d.room_no,
                       d.availability, d.available_days, d.available_time,
                       d.consultation_fee, d.phone_ext, d.is_active
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.department_id
                WHERE LOWER(dep.name) LIKE $1 AND d.is_active = TRUE
                LIMIT 5
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, f"%{dept_name.lower()}%")
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_doctors_by_department failed: {e}")
            return []

    async def find_available_doctors(self) -> List[Dict]:
        """List all currently available doctors."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT d.doctor_id, d.name, d.specialization, d.qualification,
                       d.department_id, dep.name AS dept_name,
                       d.floor, d.room_no, d.availability,
                       d.available_days, d.available_time,
                       d.consultation_fee, d.phone_ext
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.department_id
                WHERE LOWER(d.availability) = 'available' AND d.is_active = TRUE
                LIMIT 10
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_available_doctors failed: {e}")
            return []

    # ====================================================================
    # DEPARTMENTS
    # ====================================================================

    async def find_department_by_name(self, name: str) -> Optional[Dict]:
        """Find a department by name (partial match)."""
        if not self.pool:
            return None
        try:
            query = """
                SELECT department_id, name, description, floor, room_no, phone_ext, is_active
                FROM departments
                WHERE LOWER(name) LIKE $1 AND is_active = TRUE
                LIMIT 1
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, f"%{name.lower()}%")
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"find_department_by_name failed: {e}")
            return None

    async def list_departments(self) -> List[Dict]:
        """List all active departments."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT department_id, name, description, floor, room_no, phone_ext
                FROM departments
                WHERE is_active = TRUE
                ORDER BY name
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"list_departments failed: {e}")
            return []

    # ====================================================================
    # WARDS
    # ====================================================================

    async def find_wards_by_type(self, ward_type: str) -> List[Dict]:
        """Find wards by type (ICU, General, Emergency)."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT w.ward_id, w.name, w.ward_type, w.department_id,
                       dep.name AS dept_name, w.floor,
                       w.total_beds, w.available_beds, w.phone_ext
                FROM wards w
                JOIN departments dep ON w.department_id = dep.department_id
                WHERE LOWER(w.ward_type) LIKE $1 AND w.is_active = TRUE
                LIMIT 6
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, f"%{ward_type.lower()}%")
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_wards_by_type failed: {e}")
            return []

    async def find_wards_by_department(self, dept_name: str) -> List[Dict]:
        """Find wards by department name."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT w.ward_id, w.name, w.ward_type, w.department_id,
                       dep.name AS dept_name, w.floor,
                       w.total_beds, w.available_beds, w.phone_ext
                FROM wards w
                JOIN departments dep ON w.department_id = dep.department_id
                WHERE LOWER(dep.name) LIKE $1 AND w.is_active = TRUE
                LIMIT 6
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, f"%{dept_name.lower()}%")
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_wards_by_department failed: {e}")
            return []

    async def find_available_wards(self) -> List[Dict]:
        """Find wards with available beds."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT w.ward_id, w.name, w.ward_type, w.department_id,
                       dep.name AS dept_name, w.floor,
                       w.total_beds, w.available_beds, w.phone_ext
                FROM wards w
                JOIN departments dep ON w.department_id = dep.department_id
                WHERE w.available_beds > 0 AND w.is_active = TRUE
                ORDER BY w.available_beds DESC
                LIMIT 10
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_available_wards failed: {e}")
            return []

    # ====================================================================
    # NURSES
    # ====================================================================

    async def find_nurses_by_department(self, dept_name: str) -> List[Dict]:
        """Find nurses by department name."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT n.nurse_id, n.name, n.qualification,
                       n.department_id, dep.name AS dept_name,
                       n.ward_id, COALESCE(w.name, '') AS ward_name,
                       n.shift, n.phone_ext
                FROM nurses n
                JOIN departments dep ON n.department_id = dep.department_id
                LEFT JOIN wards w ON n.ward_id = w.ward_id
                WHERE LOWER(dep.name) LIKE $1 AND n.is_active = TRUE
                LIMIT 6
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, f"%{dept_name.lower()}%")
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"find_nurses_by_department failed: {e}")
            return []

    async def list_nurses(self) -> List[Dict]:
        """List all active nurses."""
        if not self.pool:
            return []
        try:
            query = """
                SELECT n.nurse_id, n.name, n.qualification,
                       n.department_id, dep.name AS dept_name,
                       n.ward_id, COALESCE(w.name, '') AS ward_name,
                       n.shift, n.phone_ext
                FROM nurses n
                JOIN departments dep ON n.department_id = dep.department_id
                LEFT JOIN wards w ON n.ward_id = w.ward_id
                WHERE n.is_active = TRUE
                LIMIT 10
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"list_nurses failed: {e}")
            return []

    # ====================================================================
    # APPOINTMENTS
    # ====================================================================

    async def find_appointment_by_patient_and_date(
        self, patient_name: str, appt_date: date
    ) -> Optional[Dict]:
        """Find appointment by patient name and date."""
        if not self.pool:
            return None
        try:
            query = """
                SELECT a.appointment_id, a.patient_name, a.patient_phone,
                       a.doctor_id, d.name AS doctor_name, d.specialization,
                       a.appointment_date, a.appointment_time,
                       a.status, a.notes
                FROM appointments a
                JOIN doctors d ON a.doctor_id = d.doctor_id
                WHERE LOWER(a.patient_name) LIKE $1
                  AND a.appointment_date = $2
                LIMIT 1
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, f"%{patient_name.lower()}%", appt_date)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"find_appointment_by_patient_and_date failed: {e}")
            return None

    async def find_appointment_by_patient(self, patient_name: str) -> Optional[Dict]:
        """Find most recent appointment by patient name (any date)."""
        if not self.pool:
            return None
        try:
            query = """
                SELECT a.appointment_id, a.patient_name, a.patient_phone,
                       a.doctor_id, d.name AS doctor_name, d.specialization,
                       a.appointment_date, a.appointment_time,
                       a.status, a.notes
                FROM appointments a
                JOIN doctors d ON a.doctor_id = d.doctor_id
                WHERE LOWER(a.patient_name) LIKE $1
                ORDER BY a.appointment_date DESC
                LIMIT 1
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, f"%{patient_name.lower()}%")
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"find_appointment_by_patient failed: {e}")
            return None

    # ====================================================================
    # BOOK APPOINTMENT
    # ====================================================================

    async def find_doctor_by_name(self, name: str) -> Optional[Dict]:
        """Find a single doctor by name (partial match) for booking."""
        if not self.pool:
            return None
        try:
            query = """
                SELECT d.doctor_id, d.name, d.specialization,
                       d.available_days, d.available_time,
                       dep.name AS dept_name
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.department_id
                WHERE LOWER(d.name) LIKE $1 AND d.is_active = TRUE
                LIMIT 1
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, f"%{name.lower()}%")
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"find_doctor_by_name failed: {e}")
            return None

    async def create_appointment(
        self,
        patient_name: str,
        patient_phone: str,
        doctor_id: int,
        appointment_date: date,
        appointment_time: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Book an appointment. Returns {success, message, appointment_id}.
        Respects uq_doctor_slot constraint (no double booking).
        """
        if not self.pool:
            return {"success": False, "message": "Database not available"}
        try:
            query = """
                INSERT INTO appointments
                    (patient_name, patient_phone, doctor_id,
                     appointment_date, appointment_time, notes)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING appointment_id
            """
            async with self.pool.acquire() as conn:
                appt_id = await conn.fetchval(
                    query,
                    patient_name, patient_phone, doctor_id,
                    appointment_date, appointment_time, notes,
                )
                return {
                    "success": True,
                    "message": "Appointment booked successfully",
                    "appointment_id": appt_id,
                }
        except asyncpg.UniqueViolationError:
            return {
                "success": False,
                "message": "That time slot is already booked. Please choose a different time.",
            }
        except Exception as e:
            logger.error(f"create_appointment failed: {e}")
            return {"success": False, "message": "Failed to book appointment"}

    # ====================================================================
    # HOSPITAL INFO (key-value table)
    # ====================================================================

    async def get_hospital_info(self) -> Dict[str, str]:
        """Get all hospital_info rows as a dict."""
        cache_key = self._cache_key("hospital_info")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        if not self.pool:
            return {}
        try:
            query = "SELECT info_key, info_value FROM hospital_info"
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                result = {r["info_key"]: r["info_value"] for r in rows}
                await self._set_cached(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"get_hospital_info failed: {e}")
            return {}

    # ====================================================================
    # HEALTH CHECK
    # ====================================================================

    async def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "database": "unknown",
            "cache": "unknown",
            "timestamp": datetime.utcnow().isoformat(),
        }
        if self.pool:
            try:
                async with self.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                status["database"] = "healthy"
            except Exception as e:
                status["database"] = f"unhealthy: {e}"
        else:
            status["database"] = "not_configured"

        if self.redis:
            try:
                await self.redis.ping()
                status["cache"] = "healthy"
            except Exception:
                status["cache"] = "unhealthy"
        else:
            status["cache"] = "not_configured"

        return status


# ── Global singleton ─────────────────────────────────────────────────────

_db_wrapper: Optional[DBWrapper] = None


async def get_db_wrapper() -> DBWrapper:
    global _db_wrapper
    if _db_wrapper is None:
        _db_wrapper = DBWrapper()
        await _db_wrapper.initialize()
    return _db_wrapper
