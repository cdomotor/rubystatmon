# File: config/initializers/statmon_log_paths.rb
# Path: /config/initializers/statmon_log_paths.rb
# Purpose: resolve a robust path for the daemon log across 'log/' vs 'logs/'
# - Prefer ENV['STATMON_DAEMON_LOG']
# - Else try Rails.root/'log/statmon_daemon.log', then 'logs/statmon_daemon.log',
#   then a fallback inside /statmon_daemon/
# - Ensure the directory exists and file is touch-created
module StatMon
  module LogPath
    module_function

    def resolve_daemon_log_path
      # 1) Explicit override via ENV
      env = ENV["STATMON_DAEMON_LOG"]
      return normalize_and_prepare(env) if env && !env.strip.empty?

      # 2) Known candidates (first existing wins; else first candidate)
      candidates = [
        Rails.root.join("log",  "statmon_daemon.log").to_s,   # Rails default
        Rails.root.join("logs", "statmon_daemon.log").to_s,   # legacy/Windows
        Rails.root.join("statmon_daemon", "statmon_daemon.log").to_s # fallback
      ]

      existing = candidates.find { |p| File.exist?(p) }
      path = existing || candidates.first
      normalize_and_prepare(path)
    end

    def normalize_and_prepare(path)
      path = File.expand_path(path.to_s) # handle weird separators on Windows
      dir  = File.dirname(path)
      FileUtils.mkdir_p(dir) unless Dir.exist?(dir)
      FileUtils.touch(path)   unless File.exist?(path)
      path
    end
  end
end
