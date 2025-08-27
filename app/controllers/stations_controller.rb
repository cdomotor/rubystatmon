# File: app/controllers/stations_controller.rb
# Path: /app/controllers/stations_controller.rb
class StationsController < ApplicationController
  before_action :set_station, only: %i[ show edit update destroy ping toggle_active ]

  require 'csv' # Ensure CSV is available for import/export

  # GET /stations
  def index
    @q      = params[:q].to_s.strip
    @status = params[:status].to_s.strip # "", "active", "reachable", "unreachable"

    scope = Station.search(@q).order(:name)

    @stations =
      case @status
      when "active"      then scope.where(active: true)
      when "reachable"   then scope.select(&:last_ping_success?)
      when "unreachable" then scope.reject(&:last_ping_success?)
      else                     scope
      end
  end

  # GET /stations/1
  def show; end

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
      respond_to do |format|
        format.turbo_stream
        format.html { redirect_to stations_path, notice: "Station created." }
      end
    else
      respond_to do |format|
        format.turbo_stream
        format.html { render :new, status: :unprocessable_entity }
      end
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

    redirect_to stations_path, notice: "Imported #{imported} station(s)."
  rescue => e
    redirect_to stations_path, alert: "Import failed: #{e.message}"
  end

  # POST /stations/:id/ping
  def ping
    respond_to do |format|
      format.turbo_stream { render turbo_stream: turbo_stream.replace(dom_id(@station), partial: "stations/station", locals: { station: @station }) }
      format.html { redirect_to stations_path, notice: "Ping requested." }
    end
  end

  # PATCH/PUT /stations/:id
  def update
    if @station.update(station_params)
      respond_to do |format|
        format.turbo_stream { render turbo_stream: turbo_stream.replace(dom_id(@station), partial: "stations/station", locals: { station: @station }) }
        format.html { redirect_to stations_path, notice: "Station updated." }
      end
    else
      respond_to do |format|
        format.turbo_stream { render turbo_stream: turbo_stream.replace(dom_id(@station), partial: "stations/station", locals: { station: @station }) }
        format.html { render :edit, status: :unprocessable_entity }
      end
    end
  end

  # PATCH /stations/:id/toggle_active
  def toggle_active
    @station.update(active: !@station.active?)
    respond_to do |format|
      format.turbo_stream { render turbo_stream: turbo_stream.replace(dom_id(@station), partial: "stations/station", locals: { station: @station }) }
      format.html { redirect_to stations_path }
    end
  end

  # DELETE /stations/:id
  def destroy
    @station.destroy
    respond_to do |format|
      format.turbo_stream { render turbo_stream: turbo_stream.remove(dom_id(@station)) }
      format.html { redirect_to stations_path, notice: "Station deleted." }
    end
  end

  private

  def set_station
    @station = Station.find(params[:id])
  end

  # PERMIT :active so PATCHes aren’t dropped as “Unpermitted parameter: :active”
  def station_params
    params.require(:station).permit(
      :name, :ip_address, :status, :notes, :active,
      :lat, :lng, :port, :auth_token
    )
  end
end
