# File: app/controllers/daemon_logs_controller.rb
# Path: /app/controllers/daemon_logs_controller.rb
class DaemonLogsController < ApplicationController
  include ActionController::Live
  require "fileutils"

  # NOTE: Rails log dir is 'log', not 'logs'
  LOG_PATH = ENV["STATMON_DAEMON_LOG"].presence || Rails.root.join("logs", "statmon_daemon.log").to_s

  def index
    redirect_to daemon_logs_show_path
  end

  def show
    @log_path = LOG_PATH
    @initial_lines = tail_lines(@log_path, max_lines: (params[:lines] || 200).to_i)
  end

  def stream
    response.headers["Content-Type"]       = "text/event-stream"
    response.headers["Cache-Control"]      = "no-cache"
    response.headers["X-Accel-Buffering"]  = "no"  # harmless if not behind nginx

    path = LOG_PATH
    FileUtils.touch(path) unless File.exist?(path)

    File.open(path, "r") do |f|
      f.seek(0, IO::SEEK_END) # start at EOF, only send new data
      loop do
        if (line = f.gets)
          data = line.encode("UTF-8", invalid: :replace, undef: :replace, replace: "?")
          response.stream.write("data: #{data}\n\n")
        else
          sleep 0.5
        end
      end
    end
  rescue IOError, ActionController::Live::ClientDisconnected
    # client went away
  ensure
    response.stream.close rescue nil
  end

  def download
    path = LOG_PATH
    return redirect_to daemon_logs_path, alert: "Log file not found." unless File.exist?(path)
    send_file path, type: "text/plain", disposition: "attachment", filename: File.basename(path)
  end

  private

  # File: app/controllers/daemon_logs_controller.rb (tail helper)
  def tail_lines(path, max_lines: 200, chunk_size: 4096)
    return [] unless File.exist?(path)

    File.open(path, "rb") do |f|
      size = f.size
      return [] if size.zero?

      lines  = []
      buffer = +""
      pos    = [size - chunk_size, 0].max

      while pos >= 0 && lines.length <= max_lines
        f.seek(pos)
        buffer = f.read([chunk_size, size].min) + buffer
        break if pos == 0
        pos -= chunk_size
      end

      buffer.each_line { |l| lines << l }
      lines.last(max_lines).map { |l| l.encode("UTF-8", invalid: :replace, undef: :replace, replace: "?") }
    end
  rescue
    []
  end
end
