# ReFind – Smart Lost & Found Platform

COSC 412 project. FastAPI + Beanie (async PyMongo) + MongoDB 7 single-node replica set; Vite + React + TypeScript + shadcn/ui front end with an Orval-generated client.

## Quick start

Requirements: Docker Desktop (with WSL integration enabled on Windows), Python 3.12+, Node 22.

```bash
cp .env.example .env              # then change the passwords
docker compose up -d              # MongoDB rs0 + MailHog; wait until "healthy"
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt

cd backend
../.venv/bin/python -m scripts.setup_db   # DB accounts + $jsonSchema validators (once; safe to re-run)
../.venv/bin/uvicorn app.main:app --reload  # creates indexes on start-up -> http://localhost:8000/docs
../.venv/bin/python -m scripts.seed --reset # 15 categories, 150 users, 600 items
../.venv/bin/python -m pytest              # tests run against refind_test
```

Seed logins: `admin@university.edu`, `officer1@university.edu` … `officer4@…`, `student001@…`; password `Password123!`.

MongoDB Compass: `mongodb://root:<MONGO_ROOT_PASSWORD>@localhost:27017/?directConnection=true`. MailHog inbox: http://localhost:8025.

### Front end

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 – /api is proxied to FastAPI on :8000
npm run api        # after ANY backend API change: export openapi.json + regenerate src/api/generated
npx shadcn@latest add dialog   # add more shadcn components as needed
```

### Auth

- Email + password (bcrypt cost 12, 60-min JWT). New accounts are `unverified` until they open the emailed link (see MailHog at http://localhost:8025); unverified users can log in but not report or claim.
- Only `ALLOWED_EMAIL_DOMAINS` can sign up. 5 failed logins per 15 min per account + IP → 429.
- **Google sign-in (optional):** in Google Cloud Console → APIs & Services → Credentials, create an *OAuth client ID* (Web application) with
  authorised redirect URI `http://localhost:5173/api/auth/google/callback`, then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env` and restart the API.
  The "Continue with Google" button appears automatically. Google accounts must be verified and in an allowed domain.
- Protect a page with `<RequireAuth roles={['officer', 'admin']}>`; protect an endpoint with `AdminUser`, `StaffUser` or `ActiveUser` from `app/deps.py`.

## Layout

```
backend/app/
  models/         Beanie documents, one per collection (camelCase = MongoDB field names)
  db_validators.py  $jsonSchema rules (database-level safety net, §5.3)
  db.py           client, init_beanie, run_in_transaction()
  security.py     bcrypt, answer normalisation, JWT
  deps.py         get_current_user, require_role (RBAC)
  services/       all writes go through here, each with an audit_service.log()
  routers/        thin HTTP layer – copy routers/categories.py
backend/scripts/  setup_db.py, seed.py
backend/tests/    pytest (integration tests against refind_test)
frontend/src/
  api/generated/  Orval hooks + types – never edit by hand
  api/fetcher.ts  adds the JWT, throws ApiError on non-2xx
  components/ui/  shadcn components
  pages/          one file per screen – copy pages/categories.tsx
  router.tsx      every §6.1 screen, with owner and milestone
```

## Conventions

- Routes never touch the database; they call a service function.
- Every write runs in `run_in_transaction()` with its audit entry, passing `session=session` to every call.
- Raise `NotFound` / `Conflict` / `Forbidden` from `app.errors`; a `DuplicateKeyError` becomes 409 automatically.
- Front end never calls fetch() directly – use the generated hooks; regenerate with `npm run api`.
- Tests empty collections with `delete_many`, never `drop` (dropping removes the validator).
- Building names are in `models/common.py` (`BUILDINGS`) – replace with the real campus list.
