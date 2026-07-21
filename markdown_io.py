"""Markdown file I/O utilities for the trip planner."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime

# Default file paths (relative to the working directory)
DEFAULT_INPUT_PATH = "trip_input.md"
DEFAULT_APPROVED_DIR = "approved_plan"
DEFAULT_CURRENT_PLAN_PATH = "current_plan.md"


def get_user_feedback_via_editor() -> str:
    """Launch the user's preferred editor to input feedback.

    Defaults to 'vim' if EDITOR is not set.
    
    Returns:
        The text entered by the user.
    """
    editor = os.environ.get("EDITOR", "vim")
    initial_content = (
        "\n\n# 上記にNGの理由やフィードバックを記述してください。\n"
        "# この行以降（#で始まる行）は無視されます。\n"
    )

    with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", encoding="utf-8", delete=False) as tf:
        tf.write(initial_content)
        tf.flush()
        filepath = tf.name

    try:
        subprocess.run([editor, filepath], check=True)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Remove comments and strip whitespace
        feedback_lines = []
        for line in lines:
            if line.startswith("#"):
                continue
            feedback_lines.append(line)
            
        return "".join(feedback_lines).strip()
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


def extract_plan_title(plan: str) -> str:
    """Extract the title from a plan's first markdown heading.

    Args:
        plan: The plan text in Markdown format.

    Returns:
        The title text, or a default if no heading is found.
    """
    match = re.search(r"^#\s+(.+)$", plan, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "（タイトルなし）"


def save_current_plan(plan: str, path: str = DEFAULT_CURRENT_PLAN_PATH) -> str:
    """Save the current plan to a markdown file and open it.

    Args:
        plan: The plan text in Markdown format.
        path: Path to save the current plan.

    Returns:
        The extracted plan title.
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(plan.strip() + "\n")

    # Open the file with the default application on macOS
    try:
        subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass  # Silently ignore if 'open' command is not available

    return extract_plan_title(plan)


def read_trip_input(path: str = DEFAULT_INPUT_PATH) -> str:
    """Read the trip input markdown file and return its full content.

    Args:
        path: Path to the trip input file.

    Returns:
        The full text content of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"入力ファイルが見つかりません: {path}\n"
            f"trip_input.md を作成してから再実行してください。"
        )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def append_feedback(feedback: str, path: str = DEFAULT_INPUT_PATH) -> None:
    """Append user feedback to the trip input file under the feedback section.

    If a '## フィードバック履歴' section exists, the feedback is appended there.
    Otherwise, a new section is created at the end of the file.

    Args:
        feedback: The feedback text to append.
        path: Path to the trip input file.
    """
    content = read_trip_input(path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- [{timestamp}] {feedback}\n"

    section_header = "## フィードバック履歴"
    if section_header in content:
        # Insert after the section header
        idx = content.index(section_header) + len(section_header)
        # Find the end of the header line
        newline_idx = content.index("\n", idx)
        updated = content[: newline_idx + 1] + "\n" + entry + content[newline_idx + 1 :]
    else:
        # Append a new section at the end
        updated = content.rstrip() + f"\n\n{section_header}\n\n{entry}"

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)


def save_approved_plan(plan: str, plan_number: int, directory: str = DEFAULT_APPROVED_DIR) -> str:
    """Save an approved plan to a new file in the specified directory.

    Args:
        plan: The plan text in Markdown format.
        plan_number: The sequential number of this approved plan.
        directory: Directory to save the approved plan.
        
    Returns:
        The path to the saved file.
    """
    os.makedirs(directory, exist_ok=True)
    now = datetime.now()
    filename = f"approved_plan_{now.strftime('%Y%m%d%H%M')}.md"
    filepath = os.path.join(directory, filename)

    header = f"## プラン #{plan_number}（承認日時: {now.strftime('%Y-%m-%d %H:%M')}）\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(plan.strip() + "\n")
        
    return filepath


def count_approved_plans(directory: str = DEFAULT_APPROVED_DIR) -> int:
    """Count the number of approved plans in the directory.

    Args:
        directory: Directory where approved plans are saved.

    Returns:
        The number of approved plans (0 if directory doesn't exist).
    """
    if not os.path.exists(directory):
        return 0
    
    count = 0
    for filename in os.listdir(directory):
        if filename.startswith("approved_plan_") and filename.endswith(".md"):
            count += 1
    return count
