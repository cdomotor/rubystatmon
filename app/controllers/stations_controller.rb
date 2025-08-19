# File: app/controllers/stations_controller.rb
# Path: /app/controllers/stations_controller.rb
class StationsController < ApplicationController
  before_action :set_station, only: %i[ show edit update destroy ping ]

  require 'csv'

  # GET /stations
  def index
    @q      = params[:q].to_s.strip
    @status = params[:status].to_s.strip # "", "reachable", "unreachable"

    @stations = Station.search(@q).order(:name)

    case @status
    when "reachable"
      @stations = @stations.select(&:last_ping_success?)
    when "unreachable"
      @stations = @stations.reject(&:last_ping_success?)
    end
  end

  # POST /stations/import
  def import
    file = params[:file]
    if file.nil?
      redirect_to stations_path, alert: "Please select a CSV file to import" and return
    end

    imported = 0
    CSV.foreach(file.path, headers: true) do |row|
      Station.create!(row.to_hash)
      imported += 1
    end

    redirect_to stations_path, notice: "Imported #{imported} station(s)"
  rescue ActiveRecord::RecordInvalid => e
    redirect_to stations_path, alert: "Import error: #{e.record.errors.full_messages.to_sentence}"
  rescue => e
    redirect_to stations_path, alert: "Import failed: #{e.message}"
  end

  # GET /stations/1
  def show
    window_start = 7.days.ago
    @battery_data = @station.series_for('Battery', since: window_start)
    @selected_params = @station.selected_parameters
    #@param_data = @selected_params.each_with_object({}) { |p, h| h[p] = @station.series_for(p, since: window_start) }
    @battery_thresholds = { low: 11.5, high: 14.5 }
  end

  # GET /stations/new
  def new
    @station = Station.new
  end

  # GET /stations/1/edit
  def edit; end

  # POST /stations
  def create
    @station = Station.new(station_params)
    if @station.save
      redirect_to @station, notice: "Station was successfully created."
    else
      render :new, status: :unprocessable_entity
    end
  end

  # PATCH/PUT /stations/1
  def update
    if @station.update(station_params)
      redirect_to @station, notice: "Station was successfully updated."
    else
      render :edit, status: :unprocessable_entity
    end
  end

  # DELETE /stations/1
  def destroy
    @station.destroy!
    redirect_to stations_path, status: :see_other, notice: "Station was successfully destroyed."
  end

  # POST /stations/1/ping
  def ping
    ip = @station.ip_address

    if Gem.win_platform?
      output  = `ping -n 1 -w 1000 #{ip}`
      success = $?.exitstatus == 0
      latency = output[/Average = (\d+)ms/, 1]&.to_i
    else
      output  = `ping -c 1 -W 1 #{ip}`
      success = $?.exitstatus == 0
      latency = output[/time=(\d+(?:\.\d+)?) ms/, 1]&.to_f&.round
    end

    @station.ping_results.create!(timestamp: Time.current, latency_ms: latency, success: success)

    respond_to do |format|
      format.turbo_stream do
        render turbo_stream: turbo_stream.replace(
          "ping_result_#{@station.id}",
          partial: "stations/ping_result",
          locals: { station: @station }
        )
      end
      format.html { redirect_to @station, notice: success ? "Ping succeeded" : "Ping failed" }
      format.json { render json: { success: success, latency_ms: latency }, status: :ok }
    end
  end

  private

  def set_station
    @station = Station.find(params[:id])
  end

  def station_params
    params.require(:station).permit(
      :name, :ip_address, :enabled,
      :filestore_path, :ingest_enabled,
      ingest_parameters: {} # allow nested JSON as a Hash
    )
  end
end
