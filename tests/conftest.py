"""Pytest fixtures for codesub tests."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_repo(temp_dir):
    """Create a temporary git repository with an initial commit."""
    repo_dir = temp_dir / "repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    # Create initial file
    test_file = repo_dir / "test.txt"
    test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    yield repo_dir


@pytest.fixture
def git_repo_with_java(temp_dir):
    """Create a git repo with a Java-like file structure."""
    repo_dir = temp_dir / "repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    # Create Java-like file structure
    java_dir = repo_dir / "src" / "main" / "java" / "com" / "example"
    java_dir.mkdir(parents=True)

    address_file = java_dir / "Address.java"
    address_file.write_text(
        """package com.example;

public class Address {
    // Address fields
    private String street;
    @Size(max=100)
    private String streetValidated;
    private String city;
    private String zip;

    public Address() {}

    public String getStreet() {
        return street;
    }
}
"""
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    yield repo_dir


def commit_changes(repo_dir: Path, message: str = "Update") -> str:
    """Commit all changes and return the commit hash."""
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_head(repo_dir: Path) -> str:
    """Get HEAD commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
