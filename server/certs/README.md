# Supabase public CA

`supabase-ca-2021.crt` is the public root CA linked by the approved project's
Supabase Dashboard → Database → Settings → SSL Configuration.

- Source: https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt
- Retrieved: 2026-09-23
- SHA256 fingerprint: `807025AD50D4ED219D2C9C7D299C004F824EB00CF7F65AFEF607D07B72E6CAFA`
- Expires: 2031-04-26 10:56:53 UTC

This is a public certificate, not a private key. The application explicitly uses
it with `sslmode=verify-full`. If Supabase rotates its CA, obtain and verify the
replacement from the official dashboard; do not turn off certificate validation.
