# File: app/controllers/daemon_logs_controller.rb
# Path: /app/controllers/daemon_logs_controller.rb
class DaemonLogsController < ApplicationController
  include ActionController::Live
  require "fileutils"

  # Resolve once per process; robust to log/ vs logs/ and ENV override
  LOG_PATH = StatMon::LogPath.resolve_daemon_log_path

  def index
    redirect_to daemon_logs_show_path
  end

  def show
    @log_path      = LOG_PATH
    @initial_lines = tail_lines(@log_path, max_lines: (params[:lines] || 200).to_i)
  end

  def stream
    response.headers["Content-Type"]      = "text/event-stream"
    response.headers["Cache-Control"]     = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # harmless without nginx

    File.open(LOG_PATH, "r") do |f|
      f.seek(0, IO::SEEK_END) # only stream new content
      loop do
        if (line = safe_gets(f))
          response.stream.write("data: #{line}\n\n")
        else
          sleep 0.5
        end
      end
    end
  rescue IOError, ActionController::Live::ClientDisconnected
    # client disconnected; exit quietly
  ensure
    response.stream.close rescue nil
  end

  def download
    return redirect_to daemon_logs_path, alert: "Log file not found." unless File.exist?(LOG_PATH)
    send_file LOG_PATH, type: "text/plain", disposition: "attachment", filename: File.basename(LOG_PATH)
  end

  private

  def safe_gets(io)
    str = io.gets
    return nil unless str
    str.encode("UTF-8", invalid: :replace, undef: :replace, replace: "?")
  end

  # Efficient tail (no shell). Returns UTF-8 strings.
  def tail_lines(path, max_lines: 200, chunk_size: 4096)
    return [] unless File.exist?(path)
    File.open(path, "rb") do |f|
      size = f.size
      return [] if size.zero?

      buf = +""
      pos = [size - chunk_size, 0].max
      while pos >= 0 && buf.count("\n") <= max_lines
        f.seek(pos)
        buf = f.read([chunk_size, size].min) + buf
        break if pos == 0
        pos -= chunk_size
      end
      buf.each_line.take_last(max_lines).map { |l| l.encode("UTF-8", invalid: :replace, undef: :replace, replace: "?") }
    end
  rescue
    []
  end
end

# Small helper for Ruby < 3.2; remove if Array#take_last exists in your version
class Array
  def take_last(n)
    self.length <= n ? self : self[-n, n]
  end
end
