# Power Detector Clarifying Questions and Answers

Last updated: 2026-03-05

This document records discovery questions for the power-loss detector and the current answers.

## Q&A Log

1. Q: Which single device will represent "house power is present"?
   A: Use a dedicated Shelly plug/relay connected to a non-UPS outlet (single sentinel strategy for v1).

2. Q: Where should the monitor process run?
   A: Raspberry Pi host on UPS power, on the same LAN as the sentinel.

3. Q: What exact phone number(s) should receive SMS alerts?
   A: User-configurable in `config.yaml` as recipient records.

4. Q: Which SMS transport is acceptable under the "zero cost" requirement?
   A: SMTP email-to-SMS gateway (phone + carrier mapping with custom domain override).

5. Q: Is one alert enough, or should repeats be sent during extended outages?
   A: User-configurable cadence; default is one outage alert + one recovery alert. Optional periodic reminders every 30 minutes.

6. Q: Should Alexa be used as a secondary local notification channel?
   A: Not in v1 scope.

7. Q: How strict should false-positive prevention be?
   A: Continuous-duration thresholds before alerts; restore windows to suppress flap noise.

8. Q: Should internet-loss events be reported separately from power-loss events?
   A: Yes, WAN-loss/WAN-restore are separate alert classes.

9. Q: What configuration format do you prefer?
   A: Single YAML config file (`config.yaml`) with defaults and overrides.

10. Q: Which operating system should deployment target first?
    A: Production target is Raspberry Pi Linux. macOS is required as a development/testing target.

## Decisions Captured During Planning Chat

11. Q: Which remote access path should be primary?
    A: Universal headless remote method is OpenSSH.

12. Q: Offsite SSH in v1?
    A: LAN-only SSH for v1.

13. Q: SSH authentication policy?
    A: Password + keys, with password auth kept enabled per user preference.

14. Q: IP/hostname strategy for reliable SSH access?
    A: DHCP reservation + hostname.

15. Q: Should all key behavior be user-configurable?
    A: Yes. Defaults are provided in `config.example.yaml`.

16. Q: Sentinel poll interval default?
    A: `10` seconds.

17. Q: Power-loss threshold default?
    A: Keep original requirement: `>= 60` seconds.

18. Q: Power-restore stability default?
    A: `10` seconds.

19. Q: WAN-loss threshold default?
    A: `90` seconds.

20. Q: WAN-restore stability default?
    A: `20` seconds.

21. Q: Event dedupe cooldown default?
    A: `180` seconds.
