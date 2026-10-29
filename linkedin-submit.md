# LinkedIn Easy Apply: stalled dialog

## What is happening

The run log shows the extension opening a job detail page, but subsequent agent
steps continue to report `page=job_detail`. In the supplied screenshot, LinkedIn
has already opened its Easy Apply dialog on the **Contact info** page. Because
the adapter does not consistently recognize that dialog as an application form,
the backend never receives the visible email, phone-country-code, phone-number,
and Next controls as an `apply_form` observation. The form workflow therefore
cannot advance.

The screenshot shows the values already populated:

- Email address
- Phone country code
- Mobile phone number

These are account contact details and should be left as they are when already
filled. The extension should only click **Next** after observing the dialog and
confirming there is no unresolved required field.

## Proposed and implemented flow

1. Recognize LinkedIn's Easy Apply dialog by its stable modal selectors, with a
   constrained fallback for an accessible dialog whose heading says
   `Apply to ...`. Do not treat arbitrary dialogs as application forms.
2. Leave **Email address**, **Phone country code**, and **Mobile phone number**
   exactly as LinkedIn currently shows them. Do not fill or change these fields,
   even when one is blank; click the currently observed **Next** control.
3. If the next page is the resume page, do not upload or select a resume. Leave
   LinkedIn's existing resume selection unchanged and click its observed
   **Review** control.
4. On the review page, click **Submit application** only when all other required
   questions have been safely resolved and an
   exact final Submit control is observed inside the Easy Apply dialog. Count an
   application as sent only after LinkedIn's confirmation is observed.
5. Use the existing answer engine, including AI fallback, for other form
   questions. If it cannot safely resolve a required question, stop that job and
   surface it in **Can't send** rather than guessing. A required non-resume
   document upload also needs the user's attention.

## Safety boundaries

- The extension does not alter or populate the three named contact fields and
  does not upload a resume in this flow.
- No database or storage migration is needed.
- Only observed controls are acted on. The adapter does not generate selectors
  or execute page-provided instructions.
- CAPTCHA, security checks, rate limits, and other platform protections remain
  hard stops. The workflow does not evade them or retry an uncertain submission.
- This fix needs a live manual check with the refreshed extension. Fixture and
  automated tests cannot prove LinkedIn's live DOM or confirmation wording.
