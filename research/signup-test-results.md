# Free cloud signup and API tests

Test date: 9 October 2026. Scope: MEGA, Blomp, Google Drive, and subsequently Filen. Isolated Chrome profiles and generated email addresses were used; no personal files were uploaded. Temporary inboxes were provided by [Mail.tm](https://mail.tm/) through its [API](https://docs.mail.tm/).

| Provider | Account creation result | Authenticated API result |
|---|---|---|
| MEGA | Created and email-activated; no phone, card, payment, or CAPTCHA requested | Passed quota, upload, listing, download with matching SHA-256, and deletion of the generated test object |
| Blomp | Not completed; image CAPTCHA rejected two completed attempts after earlier challenges expired | Not tested with credentials; public Keystone discovery responds over HTTPS |
| Google Drive | Not completed; email verification succeeded, but account creation returned a generic error after password entry | Not tested with a new account; official Drive API and OAuth setup confirmed in documentation |
| Filen | Created, email-activated, and signed in without CAPTCHA; free-storage eligibility denied | Official CLI authentication and rclone quota/listing passed; measured capacity 0 bytes, generated-file upload rejected |

## MEGA

Successful route: [register](https://mega.nz/register) → name, email, and password → activation email → confirmation link → enter password → Confirm → recovery-key screen.

The API returned **21,474,836,480 bytes total/free (20 GiB)**. rclone 1.75.2 uploaded a uniquely named generated 54-byte file, listed it, downloaded it, checked SHA-256 equality, and deleted only that generated remote object. Large-file transfers, speed, sustained rate limits, and long-term retention were not tested.

The first automation attempt dropped characters in the password field. A replacement registration succeeded with sequential typing and an exact-value check before submission. The full reusable process is saved in [MEGA-account-creation.md](MEGA-account-creation.md); the script is [cloud_signup_execute.py](cloud_signup_execute.py), and the working API test is [mega_api_test.py](mega_api_test.py). API evidence: [mega-api-test.json](signup-evidence/mega-api-test.json).

API integration can use the tested [rclone backend](https://rclone.org/mega/), or MEGA's [official SDK](https://github.com/meganz/sdk) / [MEGAcmd](https://github.com/meganz/MEGAcmd). The SDK and MEGAcmd were reviewed in documentation; they were not used for the live signup test.

## Blomp

Route: [register](https://dashboard.blomp.com/register) → name, email, password and confirmation, forum username, agreement checkbox → reCAPTCHA → Register → email activation. The test reached reCAPTCHA. No phone/card field appeared, but submission and activation were not completed. Multiple image selections were attempted with the user's explicit approval; two completed challenges were rejected and another was presented. This result does not establish that ordinary manual signup would fail.

Blomp documents [OpenStack Swift access](https://support.blomp.com/viewtopic.php?t=2622) and a [recent rclone configuration](https://support.blomp.com/viewtopic.php?t=4001). The configuration uses the account email/password, tenant `storage`, and Keystone v2 authentication. An advertised route is `https://authenticate.blomp.com/v2.0/`; the secondary HTTPS discovery host is `https://authenticate.ain.net`. Use the provider-assigned container, commonly the account email. An authenticated test must verify the object endpoint supports HTTPS with valid certificates before sending a token or files; public discovery alone does not prove file access works.

Blomp's advertised 40 GB starter allocation was not verified against an activated account. Do not yet count it as the confirmed second mirror. Discovery evidence: [blomp-api-discovery.json](signup-evidence/blomp-api-discovery.json).

## Google Drive

Route attempted: [Google signup](https://accounts.google.com/signup) → name → random adult birthday and gender, explicitly authorized by the user → Use your existing email → receive and submit verification code → password and confirmation. The email code was accepted. The next screen returned: **“Sorry, we could not create your Google Account.”** No cause was supplied. This does not prove a phone requirement or identify the email provider as the cause.

Drive's [official quickstart](https://developers.google.com/workspace/drive/api/quickstart/python) confirms a Google Cloud project, enabled Drive API, OAuth consent configuration, and an OAuth client are required for that integration route. The frontend can use a backend-held refresh token for each contributed account after authorization. Password sharing alone does not authenticate the official Drive API.

Evidence: [google-after-password.json](signup-evidence/google-after-password.json). No authenticated Drive upload or quota check was performed.

## Effect on the shared storage plan

MEGA is now a technically demonstrated candidate. Blomp remains an unverified candidate until account activation and file operations pass. Google is a documented integration candidate, but this independent signup attempt did not succeed.

Filen's later live test confirms account creation and programmatic authentication, but the account received **zero bytes of capacity**. A generated 54-byte upload was rejected with `Maximum storage reached. max_storage_reached`. The two-Filen-per-MEGA capacity calculation therefore requires legitimately eligible accounts whose quota is measured at 10 GiB. This test account supplies no capacity. Full route and evidence: [Filen-account-creation.md](Filen-account-creation.md).

For approximately 100 GB mirrored shared storage, use measured free space in contributed accounts and keep reserve capacity. Seven MEGA accounts at the observed fresh-account quota would supply 140 GiB on the MEGA side, before reserve and existing files; the second provider must separately hold the entire logical archive. Existing contributors' free capacity can be lower.

The successful small-file test is evidence of basic functionality, not a 20-year safety guarantee. Design for provider replacement, contributor departure, verified independent copies, and exported catalogue/recovery keys. Shared credentials should remain in the backend rather than being sent to every browser user.

Generated cloud and mailbox credentials remain in `test-credentials.dpapi`, encrypted with Windows DPAPI for this Windows user. MEGA's credentials were supplied to the user on request. A durable inbox and separately saved recovery key are needed before turning the research account into an archive account.
