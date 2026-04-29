import json
import subprocess
import textwrap
from typing import Any


class CodeRunner:
    WRAPPERS = {
        "python": textwrap.dedent(
            """
            import sys, json
            input_data = json.loads(sys.stdin.read())
            {user_code}
            try:
                output
            except NameError:
                pass
            else:
                print(json.dumps(output))
            """
        ),
        "javascript": textwrap.dedent(
            """
            const chunks = [];
            process.stdin.on('data', d => chunks.push(d));
            process.stdin.on('end', () => {{
                try {{
                    const input_data = JSON.parse(chunks.join(''));
                    {user_code}
                    if (typeof output !== 'undefined') {{
                        process.stdout.write(JSON.stringify(output));
                    }}
                }} catch (error) {{
                    console.error(error && error.stack ? error.stack : String(error));
                    process.exitCode = 1;
                }}
            }});
            """
        ),
    }

    def run(
        self,
        config: dict[str, Any],
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        language = str(config.get("language") or "python").strip().lower()
        user_code = config.get("code") or "output = input_data"

        if language not in self.WRAPPERS:
            raise ValueError(f"Unsupported language: {language}")

        wrapped = self.WRAPPERS[language].format(user_code=str(user_code))
        stdin_payload = json.dumps(input_data or {}).encode()

        try:
            if language == "python":
                cmd = ["python3", "-c", wrapped]
            else:
                cmd = ["node", "--input-type=module", "-e", wrapped]

            result = subprocess.run(
                cmd,
                input=stdin_payload,
                capture_output=True,
                timeout=10,
                env={"PATH": "/usr/bin:/usr/local/bin"},
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Code execution timed out (10s limit)") from exc

        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace")[:500])

        try:
            output = json.loads(result.stdout.decode())
        except json.JSONDecodeError as exc:
            raise RuntimeError("Code did not produce valid JSON output") from exc

        return output
