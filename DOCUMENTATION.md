# Polygon Migration Application

## Abstract

This Django application allows staff members to retrieve problems from Polygon and transfer problem details and test cases into the application’s database or cloud storage. The main page can be accessed at `/`. The URL configuration in `PolygonMigration/PolygonMigration/urls.py` directs it to `problems.views.index`. User login and logout functionalities are managed at `/users/login/` and `/users/logout/` through `users.views.login_view` and `users.views.logout_view`, respectively.

The main page features distinct actions for retrieving a problem, saving the primary record, storing test cases in the database, and uploading test cases to cloud storage. These actions submit to the same `index` view but with different form fields. Access to the view is limited to staff users through the use of `@user_passes_test`.

## 2.1 User Flows

### 1. User login

1. **What the user does and sends:** The user opens `/users/login/` and submits the email and password form in `users/templates/users/login.html`. The form also includes Django's CSRF token.
2. **What the backend does:** `users.views.login_view` sends the credentials to Django's `authenticate()`. `users.backends.EmailBackend.authenticate` finds the custom `users.User` by email, checks the password hash, and checks whether the account can log in. The view then checks `user.is_staff`. If an already logged-in user visits the login page, the current code logs them out before handling the request.
3. **External APIs:** None.
4. **Database and session:** The backend reads the user record. For a staff user, Django's `login()` creates an authenticated session using the configured session backend. This flow does not update profile information.
5. **What the user sees:** A staff user is sent to `/`. A non-staff user sees “You do not have staff access,” and invalid credentials show “Invalid email or password.” Logging out ends the session and returns the user to the login page.

### 2. Fetching a problem from Polygon

1. **What the user does and sends:** On the home page, the user enters a Polygon problem ID and clicks **Fetch Problem**. The `fetchForm` in `problems/templates/problems/index.html` sends `problem_id` and a CSRF token to `/`.
2. **What the backend does:** `problems.views.index` checks whether a `Problem` with that Polygon ID already exists, mainly to show its database status and tags. It creates a `PolygonAPI` client, calls `get_problem_info`, downloads and extracts the package with `download_and_extract_package`, then passes `problem.html` to `parse_problem_html`. That parser gets the statement fields such as title, legend, input/output format, and notes. The view also gets checker information, the test count, and, when available, the main solution. Test cases come from Redis if cached; otherwise, the app fetches them from Polygon. The view then renders the problem information and test previews.
3. **External APIs:** The app calls Polygon's `problem.info`, `problem.packages`, and `problem.package` for problem details and the package. It uses `problem.tests`, `problem.testInput`, and `problem.testAnswer` for test cases, and `problem.checker` for checker details. For a problem already in the database, it may also call `problem.updateWorkingCopy`, `problem.solutions`, and `problem.viewSolution` to show a main solution.
4. **Database and cache:** The view reads the `Problem` record and its tags if they exist. Fetching alone does not create or update a problem row. When Redis is available, the fetched test cases are cached by Polygon problem ID.
5. **What the user sees:** The page shows the statement, metadata, test previews, any available solution, and an error or information message. The **View Full** controls show the full fetched test fields.

### 3. Migrating a problem to the database

1. **What the user does and sends:** After fetching a problem, the user chooses a difficulty and tags and clicks **Create/Update problem in Database**. The form sends `problem_id`, `migrate_to_db=1`, `difficulty`, the selected `tags`, and a CSRF token. A tag typed into the dropdown is submitted as a selected tag by the page's JavaScript.
2. **What the backend does:** In `problems.views.index`, the view checks that a difficulty was selected. It uses cached test cases or fetches them from Polygon, then finds a `Problem` by `polygon_id`. It creates or updates the record with the parsed statement, notes, time limit, memory limit, checker type, and test count. The current code sets `constraints` and `editorial` to empty strings. It clears and recreates the tag links using `ProblemTag.get_or_create`. It then saves or updates only tests marked `is_sample` as `SampleTestCase`, using their order. Regular test cases are handled by a separate action.
3. **External APIs:** The page's fetch step calls Polygon as described above. If Redis has no test-case data, the app calls `problem.tests`, `problem.testInput`, and `problem.testAnswer`. It also tries to get the main solution using `problem.solutions` and `problem.viewSolution`.
4. **Database and cache:** The view reads and writes `problems.Problem`, `problems.ProblemTag`, and `problems.SampleTestCase`. The database changes run inside `transaction.atomic()`. Redis may be read or filled with Polygon test-case data.
5. **What the user sees:** The page shows a success message saying the problem was created or updated and keeps the fetched details visible. If an error occurs, the database transaction rolls back and the page shows an error.

### 4. Migrating test cases to the database

1. **What the user does and sends:** The user clicks **Migrate Test Description to Database**. The form sends `problem_id`, `migrate_test_cases_to_db=1`, and a CSRF token.
2. **What the backend does:** `problems.views.index` checks that a `Problem` with the Polygon ID already exists. It reads test cases from Redis or calls `get_all_test_cases` if there is no cache entry. It loads existing `ProblemTestCase` rows by order and processes each fetched test. It removes trailing whitespace and stores at most the first 260 characters of each input and output. If either value is empty, that test is skipped. Rows at existing positions are updated; additional rows are created. The code saves `is_sample`, `description`, and the order.
3. **External APIs:** On a Redis cache miss, the app calls Polygon's `problem.tests`, `problem.testInput`, and `problem.testAnswer` endpoints.
4. **Database and cache:** The view reads and writes `problems.ProblemTestCase` inside a database transaction. Redis may provide or receive the test-case data.
5. **What the user sees:** The page displays “Test cases description migrated to database Successfully.” Since the code shortens long values and skips empty ones, this message does not guarantee that every test was saved in full.

### 5. Uploading test cases to cloud storage

1. **What the user does and sends:** The user clicks **Upload Test Cases to Cloud Storage**. The form sends `problem_id`, `migrate_to_storage=1`, and a CSRF token. The button is disabled until the problem is in the database.
2. **What the backend does:** `problems.views.index` finds the `Problem` by Polygon ID, creates an `R2Storage` instance, and passes it to `PolygonAPI.migrate_test_cases_to_storage`. The migration uses the database problem ID in its object keys. It gets tests from Redis or Polygon, deletes the existing object prefix for that problem, and uploads tests that have both non-empty input and output. If there is a custom checker, `upload_custom_checker_to_storage` fetches it and uploads a compiled binary when available, or the source as a fallback. Upload errors are passed back to the caller. If uploading fails partway through, newly uploaded objects are removed.
3. **External APIs:** Polygon provides the test data and, for custom checkers, checker information and source files. `R2Storage` talks to Cloudflare R2 through its S3-compatible API.
4. **Database and storage:** The view reads the `Problem` row. Test files are stored in the configured R2 bucket, not PostgreSQL. Inputs use `test_cases/{database_problem_id}/{two_digit_test_number}` and outputs use that key plus `.a`. For example, test 1 for database problem 42 uses `test_cases/42/01` and `test_cases/42/01.a`. Custom checker files use the same problem prefix, with names such as `custom_checker.cpp`, `custom_checker.exe` on Windows, or `custom_checker` on other platforms.
5. **What the user sees:** The page shows “Test cases uploaded to cloud storage successfully.” If a custom checker was found, the result mentions it. Errors appear in the page's error panel.

## 2.2 External Integrations

### Polygon API

`problems.polygon_api.PolygonAPI` sends POST requests to `https://polygon.codeforces.com/api/{method}`. `_make_request` sends method parameters as form fields. `download_and_extract_package` also posts to `problem.package` to get the ZIP package.

Requests use `POLYGON_API_KEY` and `POLYGON_API_SECRET` from Django settings. `_generate_api_sig` adds the API key and current Unix time to a copy of the parameters, sorts and URL-encodes them, makes a random six-character prefix, and calculates a SHA-512 signature from the prefix, method name, encoded parameters, and secret. The request sends `apiKey`, `time`, and `apiSig`; it does not send the secret itself.

| Polygon endpoint | What the app uses it for |
|---|---|
| `problem.info` | Problem metadata and package context. |
| `problem.packages` | Find an available package revision and type. |
| `problem.package` | Download the standard problem package ZIP. |
| `problem.tests` | Get test indices and metadata. |
| `problem.testInput` | Get a test's input. |
| `problem.testAnswer` | Get a test's expected output. |
| `problem.checker` | Get checker type and custom-checker name. |
| `problem.viewFile` | Get custom-checker source files. |
| `problem.updateWorkingCopy` | Refresh the working copy when loading a problem that is already in the database. |
| `problem.solutions` | List solutions so the app can find a main solution. |
| `problem.viewSolution` | Get the selected solution text. |

There are also wrappers for `problem.statements`, `problem.script`, and `problem.files` in `get_statements`, `get_test_script`, and `get_problem_files`. The main page flows described above do not call these wrappers.

### Cloudflare R2

`problems.storage.R2Storage` implements the `TestCaseStorage` interface that the migration flow uses. It reads `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET_NAME`, plus optional `R2_ENDPOINT_URL` and `R2_REGION`, from Django settings populated by environment variables. The default region is `auto`. If no endpoint is set, the app can build one as `https://{account_id}.r2.cloudflarestorage.com`.

The adapter uses boto3's S3 client. It uploads with `put_object`, lists a problem's objects with paginated `list_objects_v2`, and removes old objects with `delete_objects`. boto3 signs requests using the R2 access key and secret. These credentials stay on the server in environment configuration.

The bucket is the storage container, and `test_cases/...` is the object-key prefix inside it. The slashes make the keys look like folders in the dashboard. The input/output naming format is kept, including `.a` for the output file. Custom-checker files are also kept under that problem's prefix.
