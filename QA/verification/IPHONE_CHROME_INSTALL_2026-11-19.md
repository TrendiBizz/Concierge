# iPhone Chrome install (2026-11-19)
Cause: web/portal/public/install.html treated every non-Safari iOS browser as unable to add to Home Screen (true before iOS 16.4). Jo reported Chrome on iPhone sent to Safari.
Fix: Chrome, Firefox, Edge on iOS get their own Share steps; in-app browsers, Google app and Opera still hand over to Safari.
Proof: test_iphone_chrome_firefox_edge_are_told_to_install_in_their_own_browser; mutation (regex changed) makes it fail; suite 1537 passed. NOT verified on a real iPhone.
