"""Async Supabase REST access with pooled HTTP and instance-local theme caching."""
from __future__ import annotations
import asyncio, json, logging, os, random, time
from datetime import datetime, timedelta, timezone
import aiohttp

log = logging.getLogger(__name__)
THEME_FIELDS = "id,name,description,url,platform,category,is_active,created_at"

class SupabaseError(RuntimeError): pass

class SupabaseDB:
    def __init__(self, url: str, key: str, *, theme_cache_ttl: int | None = None, page_size: int = 500):
        self.url, self.key = url.rstrip("/"), key
        self.session: aiohttp.ClientSession | None = None
        self.page_size = max(1, min(int(page_size), 1000))
        raw = os.getenv("THEME_CACHE_TTL_SECONDS", "60") if theme_cache_ttl is None else theme_cache_ttl
        try: self.theme_cache_ttl = max(0, int(raw))
        except (TypeError, ValueError): self.theme_cache_ttl = 60
        self._theme_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self._theme_locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def initialize(self) -> None:
        if self.session is not None and not self.session.closed: return
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15, connect=5, sock_read=10),
            connector=aiohttp.TCPConnector(limit=30, limit_per_host=20, keepalive_timeout=30),
            headers={"apikey":self.key,"Authorization":f"Bearer {self.key}",
                     "Content-Type":"application/json","Accept":"application/json"})
        try: await self._request("GET","themes",params={"select":"id","limit":"1"})
        except Exception:
            await self.close()
            raise

    async def _request(self, method: str, table: str, *, params=None, json=None, prefer=None):
        if self.session is None or self.session.closed: raise SupabaseError("Supabase client is not initialized")
        started=time.perf_counter()
        try:
            async with self.session.request(method,f"{self.url}/rest/v1/{table}",params=params,json=json,
                                             headers={"Prefer":prefer} if prefer else None) as response:
                body=await response.text()
                log.info("supabase_request method=%s table=%s status=%s duration_ms=%.1f",
                         method,table,response.status,(time.perf_counter()-started)*1000)
                if response.status>=400: raise SupabaseError(f"Supabase {table} request failed (HTTP {response.status})")
                if not body: return []
                try: return __import__("json").loads(body)
                except ValueError: return body
        except SupabaseError: raise
        except (aiohttp.ClientError,asyncio.TimeoutError) as exc:
            log.warning("supabase_request_failed method=%s table=%s error=%s duration_ms=%.1f",
                        method,table,type(exc).__name__,(time.perf_counter()-started)*1000)
            raise SupabaseError(f"Supabase {table} request failed: {type(exc).__name__}") from exc

    async def touch(self,user) -> None:
        now=datetime.now(timezone.utc).isoformat()
        profile={"telegram_id":user.id,"username":user.username,"first_name":user.first_name,
                 "last_name":user.last_name,"language_code":user.language_code,"last_seen_at":now}
        # The repository does not include the live users-table schema, so preserve
        # the existing first_seen_at insert/update semantics instead of assuming a DB default.
        existing = await self._request("GET","users",params={"telegram_id":f"eq.{user.id}","select":"telegram_id","limit":"1"})
        if existing:
            await self._request("PATCH","users",params={"telegram_id":f"eq.{user.id}"},json=profile,
                                prefer="return=minimal")
        else:
            profile["first_seen_at"] = now
            await self._request("POST","users",json=profile,prefer="return=minimal")
        await self._request("POST","user_states",params={"on_conflict":"telegram_id"},
                            json={"telegram_id":user.id,"last_activity":now},
                            prefer="resolution=merge-duplicates,return=minimal")

    async def _ensure_state(self,user_id: int) -> None:
        await self._request("POST","user_states",params={"on_conflict":"telegram_id"},
            json={"telegram_id":user_id,"last_activity":datetime.now(timezone.utc).isoformat()},
            prefer="resolution=merge-duplicates,return=minimal")

    async def _state_update(self,user_id: int,values: dict) -> None:
        payload=dict(values)
        payload.update(telegram_id=user_id,last_activity=datetime.now(timezone.utc).isoformat())
        await self._request("POST","user_states",params={"on_conflict":"telegram_id"},json=payload,
                            prefer="resolution=merge-duplicates,return=minimal")

    async def set_os(self,user_id: int,os_name: str) -> None:
        if os_name not in {"iOS","Android"}: raise ValueError("Unsupported OS")
        await self._state_update(user_id,{"selected_os":os_name,"selected_category":None,"current_theme_id":None})

    async def set_category(self,user_id: int,category: str) -> None:
        if category not in {"Dark","Soft","Anime","Boshqa"}: raise ValueError("Unsupported category")
        await self._state_update(user_id,{"selected_category":category,"current_theme_id":None})

    async def set_theme(self,user_id: int,theme_id: str) -> None:
        await self._state_update(user_id,{"current_theme_id":theme_id})

    async def get_state(self,user_id: int) -> dict | None:
        rows=await self._request("GET","user_states",params={"telegram_id":f"eq.{user_id}",
            "select":"telegram_id,selected_os,selected_category,current_theme_id,last_activity","limit":"1"})
        if not rows: return None
        row=rows[0]
        try:
            last=datetime.fromisoformat(row["last_activity"].replace("Z","+00:00"))
            if last<datetime.now(timezone.utc)-timedelta(seconds=3600):
                await self._request("DELETE","user_states",params={"telegram_id":f"eq.{user_id}"})
                return None
        except (ValueError,TypeError,KeyError,AttributeError): return None
        return row

    async def cleanup_expired(self,ttl_seconds: int=3600) -> int:
        cutoff=(datetime.now(timezone.utc)-timedelta(seconds=ttl_seconds)).isoformat()
        rows=await self._request("GET","user_states",params={"select":"telegram_id","last_activity":f"lt.{cutoff}","limit":"1000"})
        if not rows: return 0
        ids=[str(r["telegram_id"]) for r in rows]
        await self._request("DELETE","user_states",params={"telegram_id":f"in.({','.join(ids)})"})
        return len(ids)

    async def list_themes(self,*,platform=None,category=None,active_only=False,offset=0,limit=10):
        params={"select":"*","order":"created_at.desc","offset":str(offset),"limit":str(limit)}
        if platform: params["platform"]=f"eq.{platform}"
        if category: params["category"]=f"eq.{category}"
        if active_only: params["is_active"]="eq.true"
        return await self._request("GET","themes",params=params)

    async def get_theme(self,theme_id: str):
        rows=await self._request("GET","themes",params={"id":f"eq.{theme_id}","select":"*","limit":"1"})
        return rows[0] if rows else None

    def invalidate_theme_cache(self) -> None: self._theme_cache.clear()

    async def _load_active_themes(self,platform: str,category: str) -> list[dict]:
        result=[]; offset=0
        while True:
            page=await self._request("GET","themes",params={"select":THEME_FIELDS,"platform":f"eq.{platform}",
                "category":f"eq.{category}","is_active":"eq.true","order":"created_at.desc",
                "offset":str(offset),"limit":str(self.page_size)})
            if not isinstance(page,list): raise SupabaseError("Unexpected response while loading themes")
            result.extend(page)
            if len(page)<self.page_size: return result
            offset+=len(page)

    async def _get_active_themes(self,platform: str,category: str) -> list[dict]:
        key=(platform,category); cached=self._theme_cache.get(key)
        if cached and time.monotonic()<cached[0]:
            log.info("theme_cache result=hit platform=%s category=%s",platform,category); return cached[1]
        lock=self._theme_locks.setdefault(key,asyncio.Lock())
        async with lock:
            cached=self._theme_cache.get(key)
            if cached and time.monotonic()<cached[0]: return cached[1]
            try: rows=await self._load_active_themes(platform,category)
            except SupabaseError:
                if cached:
                    log.warning("theme_cache result=stale_fallback platform=%s category=%s",platform,category)
                    return cached[1]
                raise
            self._theme_cache[key]=(time.monotonic()+self.theme_cache_ttl,rows)
            log.info("theme_cache result=refresh platform=%s category=%s rows=%s",platform,category,len(rows))
            return rows

    async def get_random(self,platform: str,category: str,previous_id=None):
        started=time.perf_counter(); rows=await self._get_active_themes(platform,category)
        if not rows: return None
        choices=[r for r in rows if str(r.get("id"))!=str(previous_id)] or rows
        result=random.choice(choices)
        log.info("theme_selection platform=%s category=%s duration_ms=%.1f",platform,category,(time.perf_counter()-started)*1000)
        return result

    async def add_theme(self,theme: dict):
        rows=await self._request("POST","themes",json=theme,prefer="return=representation")
        if rows: self.invalidate_theme_cache(); return rows[0]
        return None

    async def update_theme(self,theme_id: str,values: dict):
        rows=await self._request("PATCH","themes",params={"id":f"eq.{theme_id}"},json=values,prefer="return=representation")
        if not rows: raise SupabaseError("Theme was not updated; it may have been deleted.")
        verified=await self.get_theme(theme_id)
        if not verified or any(verified.get(k)!=v for k,v in values.items()):
            raise SupabaseError("Theme update could not be verified.")
        self.invalidate_theme_cache()
        return verified

    async def delete_theme(self,theme_id: str):
        await self._request("PATCH","user_states",params={"current_theme_id":f"eq.{theme_id}"},
                            json={"current_theme_id":None},prefer="return=minimal")
        rows=await self._request("DELETE","themes",params={"id":f"eq.{theme_id}","select":"id"},prefer="return=representation")
        if rows: self.invalidate_theme_cache()
        return bool(rows)

    async def count(self,table: str,*,active_only=False) -> int:
        if table not in {"users","themes"}: raise ValueError("Unsupported count table")
        total=offset=0
        while True:
            params={"select":"telegram_id" if table=="users" else "id","offset":str(offset),"limit":"1000"}
            if active_only: params["is_active"]="eq.true"
            rows=await self._request("GET",table,params=params); total+=len(rows)
            if len(rows)<1000: return total
            offset+=len(rows)

    async def user_ids(self) -> list[int]:
        result=[]; offset=0
        while True:
            rows=await self._request("GET","users",params={"select":"telegram_id","order":"telegram_id","offset":str(offset),"limit":"1000"})
            result.extend(int(r["telegram_id"]) for r in rows)
            if len(rows)<1000: return result
            offset+=len(rows)

    async def close(self):
        if self.session and not self.session.closed: await self.session.close()
        self.session=None
