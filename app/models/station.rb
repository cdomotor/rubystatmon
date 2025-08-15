# File: app/models/station.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/models/station.rb

class Station < ApplicationRecord
  # Already added earlier, repeating for context:
  serialize :configured_parameters, coder: JSON

  has_many :ping_results, dependent: :destroy
  has_many :readings,     dependent: :destroy

  STALE_CUTOFF_HOURS = 24
  FAIL_WINDOW_HOURS  = 6
  FAIL_LIMIT         = 3

  def last_ping_at
    return nil unless data_source?(:ping_results)
    @last_ping_at ||= ping_results.maximum(:created_at)
  end

  def recent_failures_count(window_hours: FAIL_WINDOW_HOURS)
    return 0 unless data_source?(:ping_results)
    ping_results.where('created_at >= ?', window_hours.hours.ago)
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

  # --- NEW: concise human status for the dashboard badge line ---
  # Returns "" when all good, otherwise a semicolon-joined reason string.
  def status_summary
    reasons = []

    if data_source?(:ping_results)
      if last_ping_at.nil?
        reasons << "No pings yet"
      elsif stale?
        reasons << "Stale (>#{STALE_CUTOFF_HOURS}h)"
      end

      fails = recent_failures_count
      reasons << "Recent failures: #{fails} in #{FAIL_WINDOW_HOURS}h" if fails.positive?
    end

    # Optional thresholds check from configured_parameters
    if data_source?(:readings)
      thresholds_hash.each do |param, (min, max)|
        val = readings.where(parameter: param).order(taken_at: :desc).limit(1).pick(:value)
        next if val.nil?
        reasons << "#{param} low (#{val} < #{min})" if min && val < min
        reasons << "#{param} high (#{val} > #{max})" if max && val > max
      end
    end

    reasons.uniq.join("; ")
  rescue
    ""  # fail closed: don’t break the view if something weird happens
  end

  private

  # Accepts either:
  #   configured_parameters: { "thresholds" => { "Battery" => [11.5, 14.5], ... } }
  # or a flat { "Battery" => [11.5,14.5], ... }
  def thresholds_hash
    cfg = configured_parameters
    return {} unless cfg.is_a?(Hash)
    if cfg["thresholds"].is_a?(Hash)
      cfg["thresholds"]
    else
      cfg.select { |_k, v| v.is_a?(Array) && v.size == 2 && v.all? { |x| x.is_a?(Numeric) } }
    end
  end

  def data_source?(name)
    ActiveRecord::Base.connection.data_source_exists?(name.to_s)
  end
end
