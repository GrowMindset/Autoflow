import shutil

import pytest

from app.execution.runners.code import CodeRunner


def test_python_runner_passes_input_to_output():
    runner = CodeRunner()

    result = runner.run(
        config={
            "language": "python",
            "code": "output = dict(input_data)\noutput['processed'] = True",
        },
        input_data={"name": "Autoflow"},
    )

    assert result == {"name": "Autoflow", "processed": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_javascript_runner_passes_input_to_output():
    runner = CodeRunner()

    result = runner.run(
        config={
            "language": "javascript",
            "code": "const output = { ...input_data, processed: true };",
        },
        input_data={"name": "Autoflow"},
    )

    assert result == {"name": "Autoflow", "processed": True}


def test_python_runner_timeout_raises_runtime_error():
    runner = CodeRunner()

    with pytest.raises(RuntimeError, match="timed out"):
        runner.run(
            config={
                "language": "python",
                "code": "import time\ntime.sleep(15)\noutput = input_data",
            },
            input_data={"ok": True},
        )


def test_python_runner_missing_output_raises_json_error():
    runner = CodeRunner()

    with pytest.raises(RuntimeError, match="valid JSON output"):
        runner.run(
            config={"language": "python", "code": "processed = True"},
            input_data={"ok": True},
        )


def test_python_runner_stderr_on_syntax_error_is_raised():
    runner = CodeRunner()

    with pytest.raises(RuntimeError) as exc_info:
        runner.run(
            config={"language": "python", "code": "if True print('broken')"},
            input_data={"ok": True},
        )

    assert "SyntaxError" in str(exc_info.value)


def test_unsupported_language_raises_value_error():
    runner = CodeRunner()

    with pytest.raises(ValueError, match="Unsupported language"):
        runner.run(
            config={"language": "ruby", "code": "output = input_data"},
            input_data={"ok": True},
        )
