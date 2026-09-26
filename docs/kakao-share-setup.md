# KakaoTalk share setup

The result screen can open KakaoTalk Share directly when the Kakao JavaScript SDK is configured. Without that configuration it opens the device share sheet, then falls back to copying the invite link. None of these client APIs can confirm that the user actually sent the message.

## Kakao Developers

1. Create or select the service app in Kakao Developers.
2. Copy the **JavaScript key** from **App > Platform Key > JavaScript key**. Do not use the Native, REST API, or Admin key.
3. Register every origin that serves the game as a **JavaScript SDK domain** for that key, and register the invitation destination under **App > Product Link > Web domain**:
   - `https://google-korea-team-gemini.vercel.app`
   - each immutable Vercel Preview origin that will be tested with direct KakaoTalk Share
   - the production origin when production is approved
4. Enable KakaoTalk Share for the app if the Kakao console requests product activation.

Set `KAKAO_JAVASCRIPT_KEY` in the matching Vercel deployment environment. This key is intentionally returned by `/api/config` because Kakao's browser SDK requires it; it is an app identifier, not an Admin key or server secret.

The implementation pins Kakao JavaScript SDK `2.8.3` and calls `Kakao.Share.sendDefault()` from the existing result-page button. The shared URL keeps `link=record_share` and a new `share` ID for attribution. Tracking records the share request or chooser outcome, never a completed message delivery.

Official references:

- <https://developers.kakao.com/docs/en/javascript/download>
- <https://developers.kakao.com/docs/en/kakaotalk-share/js-link>
