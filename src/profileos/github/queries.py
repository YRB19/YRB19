REPOS_QUERY = """
query($login: String!, $cursor: String, $s7: GitTimestamp!, $s30: GitTimestamp!, $s90: GitTimestamp!) {
  user(login: $login) {
    repositories(first: 50, after: $cursor, privacy: PUBLIC, ownerAffiliations: OWNER,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name nameWithOwner url description isPrivate isFork isArchived
        createdAt pushedAt updatedAt
        primaryLanguage { name }
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
        stargazerCount forkCount
        openIssues: issues(states: OPEN) { totalCount }
        openPRs: pullRequests(states: OPEN) { totalCount }
        repositoryTopics(first: 20) { nodes { topic { name } } }
        licenseInfo { spdxId }
        defaultBranchRef {
          name
          target { ... on Commit {
            c7: history(since: $s7) { totalCount }
            c30: history(since: $s30) { totalCount }
            c90: history(since: $s90) { totalCount }
            recent: history(first: 8) { nodes {
              oid committedDate messageHeadline url changedFilesIfAvailable
              parents { totalCount }
              author { name user { login } }
            } }
          } }
        }
        releases(first: 10, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { name tagName publishedAt url isPrerelease isDraft }
        }
        mergedPRs: pullRequests(states: MERGED, first: 10, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { number title url mergedAt }
        }
      }
    }
  }
}
"""

CONTRIBUTIONS_QUERY = """
query($login: String!, $f30: DateTime!, $f365: DateTime!, $to: DateTime!) {
  user(login: $login) {
    pulse: contributionsCollection(from: $f30, to: $to) {
      totalCommitContributions totalPullRequestContributions
      totalPullRequestReviewContributions totalIssueContributions totalRepositoryContributions
      commitContributionsByRepository(maxRepositories: 100) { repository { nameWithOwner isPrivate } contributions { totalCount } }
      pullRequestContributionsByRepository(maxRepositories: 100) { repository { nameWithOwner isPrivate } contributions { totalCount } }
    }
    year: contributionsCollection(from: $f365, to: $to) {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def day_commits_query(n: int) -> str:
    """Commit counts for one closed time window across n repositories, in ONE request (aliases r0..r{n-1}).
    Owner/name travel as variables, never interpolated into the query text."""
    decl = ", ".join(f"$o{i}: String!, $n{i}: String!" for i in range(n))
    body = "\n".join(
        f"  r{i}: repository(owner: $o{i}, name: $n{i}) {{ defaultBranchRef {{ target {{ ... on Commit {{ history(since: $s, until: $u) {{ totalCount }} }} }} }} }}"
        for i in range(n))
    return f"query($s: GitTimestamp!, $u: GitTimestamp!, {decl}) {{\n{body}\n}}"
