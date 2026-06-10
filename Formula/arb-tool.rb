# Homebrew formula for arb-tool (custom tap).
#
# ── One-time setup ────────────────────────────────────────────────────────────
#   brew tap miroslavondrousek/arb-tool \
#       https://github.com/miroslavondrousek/Arbitrage-Research-Tool
#
# ── Install ───────────────────────────────────────────────────────────────────
#   brew install --HEAD arb-tool   # latest from the dev branch (works now)
#   brew install arb-tool          # latest tagged release (after v1.0.0 tag)
#
# ── Upgrade ───────────────────────────────────────────────────────────────────
#   brew reinstall --HEAD arb-tool   # HEAD installs
#   brew upgrade arb-tool            # versioned installs
#
# ── Publish a new release ─────────────────────────────────────────────────────
#   1.  Create a GitHub release tag (v1.x.y).
#   2.  curl -L <tarball-url> -o arb-tool-1.x.y.tar.gz
#   3.  shasum -a 256 arb-tool-1.x.y.tar.gz
#   4.  Update `url`, `sha256`, and `version` below.
#   5.  Commit + push — brew upgrade will pick it up.

class ArbTool < Formula
  desc "Terminal UI for real-time cross-platform prediction market arbitrage"
  homepage "https://github.com/miroslavondrousek/Arbitrage-Research-Tool"
  license "MIT"

  # ── Versioned install ──────────────────────────────────────────────────────
  # Uncomment and fill in after creating the first GitHub release:
  # url "https://github.com/miroslavondrousek/Arbitrage-Research-Tool/archive/refs/tags/v1.0.0.tar.gz"
  # sha256 "<output of: shasum -a 256 v1.0.0.tar.gz>"
  # version "1.0.0"

  # ── HEAD install (no release tag required) ────────────────────────────────
  head "https://github.com/miroslavondrousek/Arbitrage-Research-Tool.git",
       branch: "dev"

  depends_on "python@3.12"

  def install
    # Create an isolated virtualenv in the Homebrew cellar.
    # pip reads pyproject.toml and pulls all dependencies from PyPI.
    venv = virtualenv_create(libexec, "python3")
    venv.pip_install buildpath

    # Expose the arb-tool console script in Homebrew's bin/
    bin.install_symlink libexec/"bin/arb-tool"

    # Ship a reference copy of config.toml so users can diff against it
    (etc/"arb-tool").mkpath
    etc.install buildpath/"config.toml" => "arb-tool/config.toml.default"
  end

  def caveats
    <<~EOS
      All data is stored in:   ~/.arb_tool/
      Logs:                    ~/.arb_tool/arb.log

      To customise settings, copy the default config and edit it:
        mkdir -p ~/.arb_tool
        cp #{etc}/arb-tool/config.toml.default ~/.arb_tool/config.toml
        $EDITOR ~/.arb_tool/config.toml
    EOS
  end

  test do
    assert_match "arb-tool", shell_output("#{bin}/arb-tool --version")
  end
end
