from ii_structure.commands.help import execute


def test_help_full_menu():
    result = execute()
    assert "overview" in result
    assert "workflow" in result
    assert "commands" in result
    assert len(result["commands"]) == 12


def test_help_has_all_commands():
    result = execute()
    expected = {"files", "outline", "locate", "usages", "body", "imports", "search", "replace-body", "insert-symbol", "blast-radius", "dead-code", "test-coverage"}
    assert set(result["commands"].keys()) == expected


def test_help_single_command():
    result = execute("outline")
    assert result["command"] == "outline"
    assert "description" in result
    assert "when_to_use" in result
    assert "when_not_to_use" in result
    assert "cost" in result
    assert "usage" in result
    assert "tips" in result
    assert "example" in result


def test_help_unknown_command():
    result = execute("nonexistent")
    assert result is None


def test_help_all_commands_have_required_fields():
    full = execute()
    required = {"description", "when_to_use", "when_not_to_use", "cost", "usage", "example"}
    for name, cmd in full["commands"].items():
        for field in required:
            assert field in cmd, f"Command '{name}' missing required field '{field}'"


def test_help_overview_mentions_key_concepts():
    result = execute()
    overview = result["overview"]
    assert "token" in overview.lower()
    assert "yaml" in overview.lower()


def test_help_workflow_has_patterns():
    result = execute()
    workflow = result["workflow"]
    assert "locate" in workflow
    assert "outline" in workflow
    assert "usages" in workflow
    assert "grep" in workflow.lower()
