# Export the package environment (docs/14 §14.10, "Rules") into this shell.
#
#   source app/scripts/env.sh          # package from the branch name (wp/WP3 → wp3)
#   source app/scripts/env.sh wp3      # or named
#
# Works from the main checkout or any worktree. See harness-env.mjs.
_tvt_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
eval "$(node "$_tvt_env_dir/harness-env.mjs" "$@" --shell)"
unset _tvt_env_dir
