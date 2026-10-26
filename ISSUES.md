# Issues Analysis

## Summary

| Type | Critical | High | Medium | Low | Total |
|---|---:|---:|---:|---:|---:|
| Product Issues | 0 | 1 | 0 | 2 | 3 |
| Code Issues | 0 | 1 | 1 | 0 | 2 |

I ranked the issues below by how much harm they can cause and how many parts of the app they affect. The edge-case answers come from reading the code.

---

## Product Issues

---

### [P1] Problems with the same title can conflict

**Severity:** High

**Location:** `PolygonMigration/problems/views.py`, `index`, problem creation branch; `PolygonMigration/problems/models.py`, `Problem.slug`

**Description:** The view looks for an existing problem by Polygon ID, then makes a slug from the title with `slugify(title)`. Since `Problem.slug` is unique, two different Polygon problems titled “Two Sum” both get the slug `two-sum`. The second problem is not found by Polygon ID, and creating it then conflicts with the first slug.

**Impact:** The user cannot migrate an otherwise valid problem just because another problem has the same title. The database transaction fails and the page shows an error.

**Suggested Fix:** Continue using Polygon ID to identify the source problem, but make slugs unique, for example by adding a stable part of the Polygon ID. Show a useful message if a conflict still happens.

**Priority rationale:** This is first because it blocks some valid migrations, but it affects only problems whose titles collide. The first two issues can affect ordinary test migrations.

### [P2] Tag labels are difficult to select

**Severity:** Low

**Location:** `PolygonMigration/problems/templates/problems/index.html`, `tag selector`

**Description:** Currently while adding a tag, it is not clickable correctly.

**Impact:** The user faces difficulty in adding the tags.

**Suggested Fix:** Instead of using small checkbox, we can make the whole tag text clickable so that it gets added.

**Priority rationale:** This is second because it blocks some frontend functionality.

### [P3] There is no option to delete migrated data

**Severity:** Low

**Location:** PolygonMigration/problems/templates/problems/index.html, main page; PolygonMigration/problems/views.py, index

**Description:** After migrating a problem or its test cases, the user cannot delete that data from the app.

**Impact:** If the user adds the wrong problem or no longer needs the saved data, they cannot remove it from the page.

**Suggested Fix:** Add a delete option for migrated data. Ask the user to confirm before deleting so they do not remove it by accident.

**Priority rationale:** This is third because users have no simple way to clean up unwanted data, though it does not stop them from using the other features.

<!-- Keep this section to three product issues, ranked from highest to lowest priority. -->

---

## Code Issues

These issues make the backend less reliable or harder to change.

### [C1] Redis cache deletion looks for a different key

**Severity:** High

**Location:** `PolygonMigration/problems/polygon_api.py`, `store_test_cases_in_redis`, `get_test_cases_from_redis`, and `delete_problem_test_case_cache`; called from `problems.views.index`

**Description:** The app stores and reads test cases under keys starting with `polygon_migration_test_cases_{polygon_id}`, with a 30-minute expiration. Before an R2 upload, the view calls `delete_problem_test_case_cache(problem_id)`. That method searches for keys starting with `oj_dev_with_redis_storage_test_cases_{db_problem_id}`. The prefix is different, and it is passed a database ID even though the cache uses a Polygon ID. So this call does not delete the cache entry used by the next read.

**Impact:** If Polygon's test data changed recently, uploading again can use the old cached tests. The app may delete the current R2 objects and replace them with stale data.

**Suggested Fix:** Put cache-key creation in one shared helper and use the Polygon ID for reads, writes, and deletion. Make the refresh action clear the right key, and make it clear whether an action will use cached data.

**Priority rationale:** I ranked this first because the mismatch affects whether several migration actions can pick up updated test data, and it can lead directly to stale cloud files.

---

### [C2] Polygon errors can look like valid but incomplete test data

**Severity:** Medium

**Location:** `PolygonMigration/problems/polygon_api.py`, `_make_request`

**Description:** When the app asks Polygon for data, the request has no time limit. If Polygon is slow or does not respond, the app may keep waiting.

**Impact:** The user may wait a long time, and the server may have fewer resources available for other requests.

**Suggested Fix:** Set a time limit for Polygon requests. If the request takes too long, show an error so the user can try again.

**Priority rationale:** This is second because a slow request can make the app feel stuck and affect other users too.

---

<!-- Keep this section to three code issues, ranked from highest to lowest priority. -->

---

## Edge Case Analysis

### Q1

> A Polygon problem has 0 sample test cases but 15 regular test cases. What happens when you migrate this problem?

If the user clicks **Create/Update problem in Database**, the app saves the problem record and only saves tests marked as samples in `SampleTestCase`. With no sample tests, it creates no new sample rows. It also does not delete any sample rows that may already be there. This action does not save the 15 regular tests as `ProblemTestCase` rows. The user has to click **Migrate Test Description to Database** to try to save the full test list. That action can still skip empty values and shorten long input/output to 260 characters. The separate R2 upload action uploads tests that have both non-empty input and output.

---

### Q2

> A problem is migrated with 20 test cases. Later, the problem setter removes 8 test cases on Polygon (now 12 remain). The problem is re-migrated. What happens?

For **Migrate Test Description to Database**, the code updates rows for the 12 tests it receives but does not delete rows 13–20. The database can still have 20 rows. This path also does not clear Redis before reading test data.

For **Upload Test Cases to Cloud Storage**, the code calls `delete_problem_test_case_cache`, but its key pattern does not match the cache keys actually used. If the old 20-test entry is still in Redis (the cache lasts 30 minutes), the app may upload those old 20 tests again. If it gets a fresh 12-test list, it removes the old R2 prefix and uploads up to 12 tests that have complete input/output pairs.

---

### Q3

> Two different Polygon problems have the exact same title: “Two Sum.” You migrate the first one successfully. Then you try to migrate the second one. What happens?

The first problem is created with a slug based on its title, such as `two-sum`. When the second Polygon ID is submitted, the lookup by Polygon ID does not find the first problem. The app then tries to create another problem with the same unique slug. The database rejects it, the transaction rolls back, and the page shows a migration error.

---

### Q4

> When test cases are saved to the database via “Migrate Test Cases to DB”, some data is intentionally discarded. What data is lost? Why might this cause problems?

For tests that are saved, the migration removes trailing whitespace and keeps only the first 260 characters of the input and output. Any characters after that are lost. A test is skipped if its input or output is empty. The database saves the test description, sample flag, and local order, but the migration does not save Polygon's original test `index` or `manual` flag.

Shortened input or output may no longer work as a test or may give a different result. Without Polygon's original index and manual flag, it is also harder to match a database row back to its original test or understand how the test was added.

---

## Severity Guidelines

| Severity | Definition | Examples |
|---|---|---|
| **Critical** | The system is broken, there is a security vulnerability, or data is lost or corrupted. | SQL injection, authentication bypass, data corruption. |
| **High** | A major feature fails or there is a serious risk to data correctness. | A feature does not work, orphaned records, race conditions. |
| **Medium** | A feature partly works, the experience is confusing, or maintenance is difficult. | Missing validation, confusing errors, code duplication. |
| **Low** | A small or cosmetic issue, or a best-practice concern with limited impact. | Unused imports, inconsistent formatting, missing logs. |
