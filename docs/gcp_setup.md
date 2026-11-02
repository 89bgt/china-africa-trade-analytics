# GCP setup (personal account, BigQuery sandbox)

No credit card or service-account key needed.

1. In a private browser window, sign in to https://console.cloud.google.com with your **personal**
   Google account and create a project (this repo assumes the ID `china-africa-trade`).
2. Open BigQuery in that project. Without billing you are in the
   [BigQuery sandbox](https://cloud.google.com/bigquery/docs/sandbox): 10 GB storage, 1 TB queries/month,
   tables expire after 60 days, no DML. This pipeline only uses load jobs and `CREATE OR REPLACE`,
   so it runs fine; if tables expire, just rerun it.
3. Install the Google Cloud CLI (`winget install --id Google.CloudSDK -e` on Windows), reopen the terminal, then:

   ```bash
   gcloud init                                      # pick the personal account + the project
   gcloud auth application-default login            # credentials used by Python and dbt
   gcloud auth application-default set-quota-project china-africa-trade
   gcloud config list                               # check account and project
   ```

4. If your project ID differs, set `GCP_PROJECT_ID` (see `.env.example`).

dbt uses the project-local `dbt/profiles.yml` (`--profiles-dir .`), so no global `~/.dbt` profile
(e.g. a work one) is ever picked up.
