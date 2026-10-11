# Releasing `comfoconnect-pro-modbus`

Publishing a GitHub release publishes the package to PyPI. Nothing else does.

## Tags

> [!IMPORTANT]
> **Release tags must be bare versions without a leading `v`**, such as `0.1.5` or `1.0.0`.

The workflow sets the package version from the tag. The `pypi` environment only accepts tags that match `*.*.*`, so a `v0.1.5` tag cannot publish.

## Release process

1. Check that the `CI` workflow is green on `main`.
2. On GitHub, go to **Releases** > **Draft a new release**.
3. Enter the version as a new tag, for example `0.1.5`, with `main` as the target.
4. Use the version as the title and write the release notes.
5. Select **Publish release**. This starts the `Publish to PyPI` workflow. It runs the tests, sets the version from the tag and builds the wheel and source distribution.
6. Open the workflow run in the **Actions** tab. The `publish` job waits for approval in the `pypi` environment. Review it and approve the deployment.

The `publish` job then uploads the package through PyPI trusted publishing.

## PyPI setup

The PyPI project needs a trusted publisher for this repository with:

- **Workflow:** `publish.yml`
- **Environment:** `pypi`
