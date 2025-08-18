# File: app/models/station.rb
# Path: /app/models/station.rb
class Station < ApplicationRecord
  scope :active, -> { where(active: true) }
  # Persist configured_parameters as JSON; accepts Hash/Array/String
  serialize :configured_parameters, coder: JSON

  has_many :ping_results, dependent: :destroy
  has_many :readings,     dependent: :destroy

  STALE_CUTOFF_HOURS = 24
  FAIL_WINDOW_HOURS  = 6
  FAIL_LIMIT         = 3

  # Text search on name or ip_address
  scope :search, ->(q) {
    next all if q.blank?
    where("LOWER(name) LIKE ? OR LOWER(ip_address) LIKE ?", "%#{q.downcase}%", "%#{q.downcase}%")
  }

  # Accept forgiving input before validations/saves
  before_validation :normalize_tags_if_present!
  before_validation :normalize_configured_parameters!

  # --- Small helpers used by filters/UI ---

  # Prefer explicit ping timestamp, fall back to created_at
  def last_ping
    @last_ping ||= ping_results
      .order(Arel.sql("COALESCE(timestamp, created_at) DESC"))
      .limit(1).first
  end

  def last_ping_success?
    last_ping&.success
  end

  # Scalar: MAX(COALESCE(timestamp, created_at))
  def last_ping_at
    ping_results.pick(Arel.sql("MAX(COALESCE(timestamp, created_at))"))
  end

  def recent_failures_count(window_hours: FAIL_WINDOW_HOURS)
    from_time = window_hours.hours.ago
    ping_scope_between(from: from_time, to: Time.current)
      .where(success: false)
      .count
  end

  def stale?
    lp = last_ping_at
    lp.nil? || lp < STALE_CUTOFF_HOURS.hours.ago
  end

  def unhealthy?
    stale? || recent_failures_count >= FAIL_LIMIT
  end

  def status_summary
    reasons = []
    if last_ping_at.nil?
      reasons << "No pings yet"
    elsif stale?
      reasons << "Stale (>#{STALE_CUTOFF_HOURS}h)"
    end
    fails = recent_failures_count
    reasons << "Recent failures: #{fails} in #{FAIL_WINDOW_HOURS}h" if fails.positive?
    reasons.uniq.join("; ")
  rescue
    ""
  end

  # --- Lightweight metrics/series API for charts/sparklines ---

  # Returns [[epoch_ms, latency_ms], ...] in ascending time, ignoring nils.
  def ping_series(from: 24.hours.ago, to: Time.current)
    rows = ping_scope_between(from:, to:)
             .where.not(latency_ms: nil)
             .order(Arel.sql("COALESCE(timestamp, created_at) ASC"))
             .pluck(:timestamp, :created_at, :latency_ms)

    rows.map do |t, created_at, v|
      ts = (t || created_at).to_i * 1000
      [ts, v]
    end
  end

  # Returns [[epoch_ms, 1/0], ...] for success state over time.
  def ping_success_series(from: 24.hours.ago, to: Time.current)
    rows = ping_scope_between(from:, to:)
             .order(Arel.sql("COALESCE(timestamp, created_at) ASC"))
             .pluck(:timestamp, :created_at, :success)

    rows.map do |t, created_at, ok|
      ts = (t || created_at).to_i * 1000
      [ts, ok ? 1 : 0]
    end
  end

  # Generic accessor for views; flexible window args
  def series_for(key, from: nil, to: nil, since: nil, hours: nil, last: nil)
    _from, _to = resolve_window(from:, to:, since:, hours:, last:)

    case key.to_s
    when "latency", "latency_ms", "latency_24h"
      ping_series(from: _from, to: _to)
    when "success", "success_24h"
      ping_success_series(from: _from, to: _to)
    else
      []
    end
  end

  # Returns an Array<String> of parameter names the station cares about.
  def selected_parameters
    cp = configured_parameters

    case cp
    when Hash
      if cp["selected"].is_a?(Array)
        cp["selected"].map(&:to_s)
      elsif cp["parameters"].is_a?(Array)
        cp["parameters"].map(&:to_s)
      else
        (cp.keys - ["thresholds"]).map(&:to_s)
      end
    when Array
      cp.map(&:to_s)
    when String
      cp.split(/[,;\s]+/).map(&:strip).reject(&:blank?)
    else
      []
    end
  end

  private

  # Unified time-window scope that binds through `where(...)` correctly.
  # IMPORTANT: do NOT wrap the SQL string in Arel.sql here, so the `?` binds are handled by AR.
  def ping_scope_between(from:, to:)
    ping_results.where(
      "COALESCE(timestamp, created_at) BETWEEN ? AND ?",
      from, to
    )
  end

  # Accepts various window styles and normalises to [from, to]
  def resolve_window(from:, to:, since:, hours:, last:)
    return [from, to] if from && to
    return [since, Time.current] if since

    if hours
      return [hours.to_i.hours.ago, Time.current]
    end

    if last
      duration =
        case last
        when ActiveSupport::Duration then last
        when Numeric then last.seconds
        else 24.hours
        end
      return [Time.current - duration, Time.current]
    end

    [24.hours.ago, Time.current]
  end

  # ---------- Normalisers ----------

  def normalize_tags_if_present!
    return unless has_attribute?(:tags) && self[:tags].present?
    tokens = self[:tags].to_s.split(/[,;\s]+/).map(&:strip).reject(&:blank?)
    self[:tags] = tokens.uniq.join(",")
  end

  def normalize_configured_parameters!
    raw = self[:configured_parameters]
    return if raw.nil? || raw.is_a?(Hash) || raw.is_a?(Array)

    str = raw.to_s.strip
    parsed =
      begin
        val = JSON.parse(str)
        (val.is_a?(Array) || val.is_a?(Hash)) ? val : [val]
      rescue JSON::ParserError
        str.split(/[,;\s]+/).map(&:strip).reject(&:blank?)
      end

    self[:configured_parameters] = parsed
  end

  def thresholds_hash
    cfg = configured_parameters
    return {} unless cfg.is_a?(Hash)
    if cfg["thresholds"].is_a?(Hash)
      cfg["thresholds"]
    else
      cfg.select { |_k, v| v.is_a?(Array) && v.size == 2 && v.all? { |x| x.is_a?(Numeric) } }
    end
  end
end
