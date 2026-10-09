# Email backup pairs

Prepared on 9 October 2026 for ten randomly generated test names.

The password CSV and screenshots that expose passwords stay local and are excluded from Git. The JSON manifest contains no passwords.

`email-pairs.csv` and `email-pairs.json` preserve the exact pairings and current signup status. An address marked `planned` has not been registered. The user reports all ten Proton inboxes created. On 9 October 2026, one sign-in attempt for Lena (`lena.lindner.6760@proton.me`) returned "Account suspended" by Proton's automated anti-abuse system. No MEGA signup for Lena was submitted because activation requires access to her inbox. The other nine Proton inboxes have not been independently checked. Each pair uses different usernames at Mailfence and Proton. The Mailfence addresses remain proposals; their availability has not been checked. All generated passwords are preserved.

Earlier automated email account creation was stopped at the user's request, and the user took over registrations. The retired Outlook proposal reached the country and birthday form. The earlier Proton signup attempt was rejected with a network traffic / further-signups block. The later Lena sign-in suspension is recorded in `../research/signup-evidence/lena-proton-login-result.json`. Proton provides an [appeal form](https://proton.me/support/appeal-abuse); no appeal has been submitted.

Mailfence is the Outlook alternative selected after research. Its [free plan](https://blog.mailfence.com/best-free-email-providers/) includes 500 MB of email storage, which is sufficient for activation and recovery mail. Its [company](https://www2.mailfence.com/en/company.jsp) has operated since 1999, with email software licensing for businesses and universities. This is evidence of operating history, not a guarantee of future survival. Its initial [signup form](https://mailfence.com/registration/?lg=en) was inspected without submission: name, username, password/confirmation, terms, and age confirmation. The generated passwords fit the observed 10-character minimum and 255-character maximum. Later verification steps remain untested; use the paired Proton inbox for activation/recovery if requested.

Mailfence free accounts are [suspended after seven months without activity and deleted five months later](https://kb.mailfence.com/kb/what-should-i-do-if-my-account-has-been-locked/). Log in to each inbox at least every six months. GMX was also checked, but its [registration instructions](https://support.gmx.com/account/login-details/register.html) require a mobile number.

Generated passwords and adult birthdays are stored under `permanent_mail_pairs` in `../research/test-credentials.dpapi`, encrypted with Windows DPAPI for the current Windows user. At the user's request, `email-pairs.csv` includes `password_a` and `password_b` in plaintext, next to each proposed email address. These are passwords to use during manual signup, not proof that the accounts already exist. The JSON manifest excludes passwords.

Pairing two addresses is a record of intended backup partners. It does not automatically configure mutual recovery, forward emails, or replicate cloud files. Those actions must be recorded separately once completed.

Mail.tm's [FAQ](https://mail.tm/en/faq/) says mailboxes remain valid until deleted, domains are renewed, and incoming messages are retained for seven days. It offers no outgoing email or forgotten-password reset. Two inboxes at this provider share its availability risk.

If Mail.tm stops operating, all inboxes there could lose incoming email together. That event would not by itself delete accounts or files at a separate cloud provider. Saved credentials may still allow normal login, but an email verification or recovery step could block access. Saving a cloud recovery key does not guarantee that all email-dependent recovery steps can be completed.
