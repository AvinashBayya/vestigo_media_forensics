# C2PA test sample

`adobe-20220124-C.jpg` is used to test C2PA / Content Credentials **detection**. It is copied
unchanged from the C2PA public test files.

| | |
|---|---|
| Source | https://github.com/c2pa-org/public-testfiles/blob/main/legacy/1.4/image/jpeg/adobe-20220124-C.jpg |
| Upstream commit | `2f7aacf1b10bc6225741215a6e9d821285b04925` |
| Creator | Adobe, contributed to the C2PA public test files |
| Licence | [Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/) |
| Changes | None |
| SHA-256 | `75a8da33f6eaf1e16bf3b42cd78913b22b2e6a671fda217a508b1ba4230ce864` |

Upstream notes that the Content Credentials in the Adobe samples were added with the C2PA Tool's
test certificate, which is not on any trust list. That makes it a useful reminder that detecting a
manifest says nothing about whether it validates, who signed it, or whether the content is
authentic. Vestigo Milestone 1 performs detection only.
