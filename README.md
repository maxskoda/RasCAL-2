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

To start a model from scratch, open **Edit Project → Custom Files → New model
file…**. Choose a new `.py` (Python) or `.m` (MATLAB) filename outside the bundled
examples. RasCAL2 creates an empty file, adds it to the draft project's Custom
Files list, and opens a blank editor. Existing files are never overwritten by
this action; use **Edit File** to edit one instead.

Click **Model Assistant** and describe the model you want, its parameter order,
and whether it is a custom layers or custom XY model. Ask for the complete file
in one fenced code block. Review and apply the suggestion, then click **Save**
in the editor. The function choices in the Custom Files table are refreshed
after saving. Finish applying your project edits and assign the custom file to
the relevant contrasts before running a calculation. An empty file is not yet a
runnable model. Cancelling project edits does not delete files created on disk.

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

### Google Vertex AI using your IRIS-IAM login

Pull the `model-assistant` branch and install its updated dependencies in your
PyCharm project environment:

```powershell
python -m pip install -r requirements.txt
```

Complete your organisation's IRIS-IAM group approval and Google Cloud CLI login
on the same Windows account that runs PyCharm. If you have already created the
login configuration in your user folder, authenticate with:

```powershell
gcloud auth application-default login --login-config="$env:USERPROFILE\gcloud-auth-config.json"
gcloud config set project prj-d-isis-vtxai-wc5y
```

Wait until the terminal confirms that credentials have been saved. Do not copy
the credentials file into the repository or paste an access token into RasCAL2.
The organisation's quota-project warning can be ignored as directed in its setup
instructions; if ADC already specifies a quota project, the assistant preserves it.

Restart RasCAL2, open a custom model in its built-in editor, and click **Model
Assistant**. Set:

| Field | Value |
| --- | --- |
| Provider | Google Vertex AI (ADC) |
| Google project | `prj-d-isis-vtxai-wc5y` |
| Vertex location | `global` |
| Model | An enabled Gemini model, for example `google/gemini-2.5-flash` if available to your project |

Click **Save connection settings** to remember the provider, Google project,
location and model on this computer. These preferences are restored when you
reopen the editor or restart RasCAL2, and model names are remembered separately
for Vertex and OpenAI-compatible providers. Previously saved preferences take
precedence over environment-variable defaults. API keys, Google credentials,
prompts and shared code are not saved by this button. The custom API base URL
is still configured in the panel or through `RASCAL_ASSISTANT_URL`.

The API key and custom base URL fields are disabled for Vertex AI. Its endpoint
is built from the project and location. Bare Gemini IDs such as
`gemini-2.5-flash` are also accepted. This provider uses Vertex's OpenAI-compatible
Gemini API; Anthropic models on Vertex are not supported by this connection.
Regional locations such as `europe-west4` can be used when the chosen model and
your organisation's policy support them. A `global` location does not guarantee
that processing stays in Europe.

Start with **No editor code** and send “Reply with a short hello.” This tests
the actual model connection without sharing a model file. Then choose **Selected
code** or **Whole file** for model-writing help. The existing review, syntax
check, apply and undo workflow is unchanged.

The assistant loads local Application Default Credentials through `google-auth`
and refreshes access tokens as needed in its background worker. It does not
launch a browser or store tokens in RasCAL2 settings. Optional defaults for the
project and location come from `GOOGLE_CLOUD_PROJECT` and
`GOOGLE_CLOUD_LOCATION`; set these in the PyCharm run configuration if desired.
`GOOGLE_APPLICATION_CREDENTIALS`, if set, overrides gcloud's usual ADC file;
check it if RasCAL2 appears to use an unexpected identity. The
`gcloud-auth-config.json` login configuration is not itself the saved ADC file.

If the institutional session expires (the supplied instructions specify 16
hours), rerun the login command above and retry **Send**. Missing or expired
ADC produces a login hint. HTTP 403 requires checking project/group/model
permissions; HTTP 404 may mean an incorrect or unavailable model/location.
Changing the active gcloud project alone does not grant access. The worker's
ADC and Vertex behavior is covered by simulated-credential/HTTP tests; a live
institutional connection must be validated on your authenticated computer.
