"""SQLite repository for candidate profile proposals and versions."""

import hashlib
import json
from datetime import datetime

from src.domain.candidate import CandidateProfile, CandidateProfileProposal
from src.storage.database import Database


def _canonical_payload(model: CandidateProfileProposal) -> str:
    return json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class CandidateRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_proposal(
        self,
        run_id: str,
        proposal: CandidateProfileProposal,
    ) -> CandidateProfileProposal:
        payload = _canonical_payload(proposal)
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.database._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_profile_proposals (
                    id, run_id, payload_json, content_hash, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    proposal.id,
                    run_id,
                    payload,
                    content_hash,
                    proposal.created_at.isoformat(),
                ),
            )
        return proposal

    def confirm(
        self,
        proposal_id: str,
        *,
        confirmed_at: datetime,
    ) -> CandidateProfile:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json, content_hash, status
                FROM candidate_profile_proposals WHERE id = ?
                """,
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(proposal_id)
            if row["status"] != "pending":
                raise ValueError("proposal is not pending")

            proposal = CandidateProfileProposal.model_validate_json(
                row["payload_json"]
            )
            version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM candidate_profiles"
            ).fetchone()[0]
            profile = CandidateProfile(
                id=f"profile-{version}",
                version=version,
                verified_facts=proposal.verified_facts,
                fact_evidence=proposal.fact_evidence,
                target_roles=proposal.target_roles,
                preferences=proposal.preferences,
                exclusions=proposal.exclusions,
                writing_style=proposal.writing_style,
                source_documents=proposal.source_documents,
                star_examples=proposal.star_examples,
                created_at=proposal.created_at,
                confirmed_at=confirmed_at,
                content_hash=row["content_hash"],
            )
            conn.execute(
                "UPDATE candidate_profiles SET is_active = 0 "
                "WHERE is_active = 1"
            )
            conn.execute(
                """
                INSERT INTO candidate_profiles (
                    id, version, payload_json, content_hash, is_active,
                    created_at, confirmed_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    profile.id,
                    profile.version,
                    profile.model_dump_json(),
                    profile.content_hash,
                    profile.created_at.isoformat(),
                    confirmed_at.isoformat(),
                ),
            )
            conn.execute(
                """
                UPDATE candidate_profile_proposals
                SET status = 'confirmed', confirmed_at = ?
                WHERE id = ?
                """,
                (confirmed_at.isoformat(), proposal_id),
            )
        return profile

    def get_active(self) -> CandidateProfile | None:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM candidate_profiles "
                "WHERE is_active = 1"
            ).fetchone()
        if row is None:
            return None
        return CandidateProfile.model_validate_json(row["payload_json"])

    def versions(self) -> list[CandidateProfile]:
        with self.database._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM candidate_profiles ORDER BY version"
            ).fetchall()
        return [
            CandidateProfile.model_validate_json(row["payload_json"])
            for row in rows
        ]
