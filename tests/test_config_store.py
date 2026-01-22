"""Tests for ConfigStore."""

import json

import pytest

from codesub.config_store import ConfigStore
from codesub.errors import ConfigExistsError, ConfigNotFoundError, SubscriptionNotFoundError
from codesub.models import Subscription


class TestConfigStore:
    """Tests for ConfigStore class."""

    def test_init_creates_config(self, temp_dir):
        store = ConfigStore(temp_dir)
        config = store.init("abc123")

        assert store.exists()
        assert config.repo.baseline_ref == "abc123"
        assert config.subscriptions == []
        assert config.schema_version == 1

    def test_init_force_overwrites(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")
        config = store.init("def456", force=True)

        assert config.repo.baseline_ref == "def456"

    def test_init_without_force_raises(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        with pytest.raises(ConfigExistsError):
            store.init("def456", force=False)

    def test_load_not_found_raises(self, temp_dir):
        store = ConfigStore(temp_dir)

        with pytest.raises(ConfigNotFoundError):
            store.load()

    def test_add_and_list_subscription(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        sub = Subscription.create(
            path="test.py",
            start_line=10,
            end_line=20,
            label="Test subscription",
        )
        store.add_subscription(sub)

        subs = store.list_subscriptions()
        assert len(subs) == 1
        assert subs[0].path == "test.py"
        assert subs[0].start_line == 10
        assert subs[0].end_line == 20
        assert subs[0].label == "Test subscription"

    def test_remove_subscription_soft(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        sub = Subscription.create(path="test.py", start_line=10, end_line=20)
        store.add_subscription(sub)

        removed = store.remove_subscription(sub.id[:8], hard=False)
        assert removed.active is False

        # Should not appear in active list
        active = store.list_subscriptions(include_inactive=False)
        assert len(active) == 0

        # Should appear when including inactive
        all_subs = store.list_subscriptions(include_inactive=True)
        assert len(all_subs) == 1
        assert all_subs[0].active is False

    def test_remove_subscription_hard(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        sub = Subscription.create(path="test.py", start_line=10, end_line=20)
        store.add_subscription(sub)

        store.remove_subscription(sub.id[:8], hard=True)

        all_subs = store.list_subscriptions(include_inactive=True)
        assert len(all_subs) == 0

    def test_remove_subscription_not_found_raises(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        with pytest.raises(SubscriptionNotFoundError):
            store.remove_subscription("nonexistent")

    def test_get_subscription_by_prefix(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        sub = Subscription.create(path="test.py", start_line=10, end_line=20)
        store.add_subscription(sub)

        found = store.get_subscription(sub.id[:4])
        assert found.id == sub.id

    def test_update_baseline(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        store.update_baseline("def456")

        assert store.get_baseline() == "def456"

    def test_roundtrip_preserves_data(self, temp_dir):
        store = ConfigStore(temp_dir)
        store.init("abc123")

        from codesub.models import Anchor

        sub = Subscription.create(
            path="path/to/file.py",
            start_line=42,
            end_line=45,
            label="Test label",
            description="Test description",
            anchors=Anchor(
                context_before=["before 1", "before 2"],
                lines=["line 1", "line 2", "line 3", "line 4"],
                context_after=["after 1", "after 2"],
            ),
        )
        store.add_subscription(sub)

        # Reload and verify
        config = store.load()
        loaded_sub = config.subscriptions[0]

        assert loaded_sub.id == sub.id
        assert loaded_sub.path == sub.path
        assert loaded_sub.start_line == sub.start_line
        assert loaded_sub.end_line == sub.end_line
        assert loaded_sub.label == sub.label
        assert loaded_sub.description == sub.description
        assert loaded_sub.anchors.lines == sub.anchors.lines
