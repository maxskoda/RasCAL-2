# RasCAL-2
GUI for Reflectivity Algorithm Toolbox (RAT)

This GUI is a PyQt6-based frontend to the Python RAT API available here: https://github.com/RascalSoftware/python-RAT
There is also a MATLAB API available here: https://github.com/RascalSoftware/RAT

## Model Assistant

Open a custom model in the built-in editor and click **Model Assistant**. The
panel can explain code, help draft a model, or propose a complete replacement.
Choose an OpenAI-compatible API base URL and model name, and enter its API key
if required. Hosted providers use HTTPS; local providers can use a loopback URL
such as `http://127.0.0.1:1234/v1`. The provider must support streamed Chat
Completions. No additional backend service is bundled.

You can also supply defaults through `RASCAL_ASSISTANT_URL`,
`RASCAL_ASSISTANT_MODEL`, and `RASCAL_ASSISTANT_API_KEY`. Keys are held in memory,
not written to project files or application settings. Set them through your
normal secure environment configuration rather than checking them into Git.

Each **Send** submits your prompt and the selected context to the configured
provider. Editor code is excluded by default. Choose **Selected code** or
**Whole file** to share it explicitly. The optional bundled Python custom
layers example provides a RAT reference for template-based generation. Project
parameters, experimental data, and other files are never attached automatically;
include relevant parameter order and constraints in your prompt when needed.
Requests are independent, so include context again when asking a follow-up.
Responses are not saved as conversation history.

To request an edit, ask for a complete replacement in a single fenced code
block. Review the proposed diff, then click **Apply reviewed replacement to
editor**. Python replacements receive a syntax check; no generated code is
executed and scientific correctness is not verified. Apply is disabled if the
response fails or the editor has changed since the request. Applying is undoable
and does not save the file: use the editor's **Save** button after review. MATLAB
responses can be reviewed too, but do not receive a Python syntax check.

**Cancel** stops receiving the response and prevents partial code from being
applied. A stalled connection may take up to the network read timeout (30
seconds) to return; closing the editor during a request cancels it first. No
provider request is made until you click **Send**.
