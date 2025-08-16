# File: app/models/station.rb
# Path: /app/models/station.rb
class Station < ApplicationRecord
  # Persist configured_parameters as JSON; accepts Hash/Array/String
  serialize :configured_parameters, coder: JSON

  has_many :ping_results, dependent: :destroy
  has_many :readings,     dependent: :destroy

  STALE_CUTOFF_HOURS = 24
  FAIL_WINDOW_HOURS  = 6
  FAIL_LIMIT         = 3

  # Text search on name or ip_address (kept from your version)
  scope :search, ->(q) {
    next all if q.blank?
    where("LOWER(name) LIKE ? OR LOWER(ip_address) LIKE ?", "%#{q.downcase}%", "%#{q.downcase}%")
  }

  # Accept forgiving input before validations/saves
  before_validation :normalize_tags_if_present!
  before_validation :normalize_configured_parameters!

  # --- Small helpers used by filters/UI ---
  def last_ping
    @last_ping ||= ping_results.order(created_at: :desc).limit(1).first
  end

  def last_ping_success?
    last_ping&.success
  end

  def last_ping_at
    ping_results.maximum(:created_at)
  end

  def recent_failures_count(window_hours: FAIL_WINDOW_HOURS)
    ping_results.where('created_at >= ?', window_hours.hours.ago).where(success: false).count
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
    last_ping_at.nil? ? reasons << "No pings yet" : reasons << "Stale (>#{STALE_CUTOFF_HOURS}h)" if stale?
    fails = recent_failures_count
    reasons << "Recent failures: #{fails} in #{FAIL_WINDOW_HOURS}h" if fails.positive?
    reasons.uniq.join("; ")
  rescue
    ""
  end

  # Extract threshold pairs either from a nested "thresholds" hash
  # or from top-level { "Param" => [low,high], ... }
  private

  def thresholds_hash
    cfg = configured_parameters
    return {} unless cfg.is_a?(Hash)
    if cfg["thresholds"].is_a?(Hash)
      cfg["thresholds"]
    else
      cfg.select { |_k, v| v.is_a?(Array) && v.size == 2 && v.all? { |x| x.is_a?(Numeric) } }
    end
  end

  # ---------- Normalisers ----------
  # Make tags forgiving: "a, b  c;d" -> "a,b,c,d"
  def normalize_tags_if_present!
    return unless has_attribute?(:tags) && self[:tags].present?
    tokens = self[:tags].to_s.split(/[,;\s]+/).map!(&:strip).reject!(&:blank?) || []
    self[:tags] = tokens.uniq.join(",")
  end

  # Accept JSON array, JSON object, or a simple comma/space-separated list
  # Stores Hash/Array directly (serialize handles it) or JSON text if the column is plain text.
  def normalize_configured_parameters!
    raw = self[:configured_parameters]
    return if raw.nil? || (raw.is_a?(Hash) || raw.is_a?(Array))

    str = raw.to_s.strip
    parsed =
      begin
        val = JSON.parse(str)
        # If parsed is scalar, wrap to array
        val.is_a?(Array) || val.is_a?(Hash) ? val : [val]
      rescue JSON::ParserError
        # Fallback: split into array of strings
        str.split(/[,;\s]+/).map(&:strip).reject(&:blank?)
      end

    # If the column is backed by serialize(JSON), assigning Array/Hash is ideal.
    self[:configured_parameters] = parsed
  end
end
