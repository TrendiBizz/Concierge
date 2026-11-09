# TikTok App Review — genuine Login Kit sandbox recording

This is a recording plan, **not** a substituted or simulated demonstration. Record the running customer portal and TikTok's real sandbox authorization screens.

## Reduce requested products to what actually works
For this first review, select **Login Kit for Web** with `user.info.basic` only. Remove Share Kit, Display API, Content Posting API and `video.publish` until those features can be shown end-to-end. The existing Rust connector is for account linking; it does not publish videos.

## TikTok sandbox prerequisites
1. TikTok Developer Portal > Trendi Concierge app > Sandbox.
2. Products > Login Kit > Web: callback must be exactly `https://concierge.trendibizz.com/owner/social/oauth/callback`.
3. Scopes: `user.info.basic`. Add your own TikTok test account under Sandbox settings > Target users.
4. Put the **sandbox** Client Key, Client Secret and callback in private `.private/oauth-staging/social.env` as `SOCIAL_TIKTOK_CLIENT_KEY`, `SOCIAL_TIKTOK_CLIENT_SECRET`, `SOCIAL_TIKTOK_CALLBACK`. Never show credentials in the video, Git, or browser UI.
5. Restart **staging Rust social service only** and verify TikTok provider readiness is true. Publishing flags stay false.
6. Confirm the owner portal TikTok button is enabled and a real sandbox authorization returns a connected account record.

## Suggested screen recording (about 1–2 minutes)
1. Begin in Chrome displaying the address bar with `https://concierge.trendibizz.com/owner-ui`.
2. Show the already signed-in test business owner; avoid exposing session credentials.
3. Scroll to Social publishing and show `Connect TikTok`.
4. Click Connect TikTok. The real TikTok sandbox Login Kit authorization dialog should appear.
5. Display the requested `user.info.basic` permission, without recording any password being typed.
6. Approve access using a registered TikTok sandbox target user.
7. Return to Concierge; show TikTok listed under the connected accounts, with the account display name.
8. Explain that this permission reads the authorized basic profile identity and that posting remains disabled. Do not portray video publishing unless that product is implemented and approved.
9. Optional: demonstrate Disconnect, then reconnect if it helps review. Avoid exposing access tokens.

## Record and compress
Press **Shift + Command + 5** on Mac, choose **Record Entire Screen** or **Record Selected Portion**, select Options to hide the microphone if no narration is needed, and start. Avoid recording secrets, other browser tabs and personal messages. End with Stop in the menu bar.

Run:
```zsh /Users/jo/work-staging/concierge-integration/scripts/prepare-tiktok-review-video.zsh "/path/to/actual/recording.mov"
```
The MP4 will be written to:
`/Users/jo/work-staging/concierge-integration/QA/verification/tiktok-review/Trendi_Concierge_TikTok_LoginKit_Sandbox_Review.mp4`

Check the result visually and confirm it is under **50 MB** before uploading. The website in the video must match the website URL in the Developer Portal.

## Suggested review description
Trendi Concierge provides business owners with a centralized portal to connect approved social accounts. The web Login Kit integration redirects the signed-in business owner to TikTok to consent to `user.info.basic`. Following approval, Concierge exchanges the one-time code on its backend, verifies the returned TikTok account identity, and stores the user credentials encrypted and scoped to the customer's business. The linked account is visible only to that business. This application is requesting basic account linking only; TikTok content posting is not enabled in this review.

## TikTok source
https://developers.tiktok.com/docs/en/app-review-guidelines
https://developers.tiktok.com/docs/en/add-a-sandbox
