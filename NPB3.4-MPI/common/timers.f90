!---------------------------------------------------------------------
!---------------------------------------------------------------------

module timers

  double precision start(64), elapsed(64)

end module timers

!---------------------------------------------------------------------
!---------------------------------------------------------------------

subroutine timer_clear(n)

!---------------------------------------------------------------------
!---------------------------------------------------------------------

  use timers
  implicit none

  integer n

  elapsed(n) = 0.0
  return
end

!---------------------------------------------------------------------
!---------------------------------------------------------------------

subroutine timer_start(n)

!---------------------------------------------------------------------
!---------------------------------------------------------------------

  use :: mpi, only:mpi_wtime
  use timers
  implicit none

  integer n

  start(n) = MPI_Wtime()

  return
end

!---------------------------------------------------------------------
!---------------------------------------------------------------------

subroutine timer_stop(n)

!---------------------------------------------------------------------
!---------------------------------------------------------------------

  use :: mpi, only:mpi_wtime
  use timers
  implicit none

  integer n

  double precision t, now

  now = MPI_Wtime()
  t = now - start(n)
  elapsed(n) = elapsed(n) + t

  return
end

!---------------------------------------------------------------------
!---------------------------------------------------------------------

double precision function timer_read(n)

!---------------------------------------------------------------------
!---------------------------------------------------------------------

  use timers
  implicit none

  integer n

  timer_read = elapsed(n)

  return
end

!---------------------------------------------------------------------
!---------------------------------------------------------------------

subroutine check_timer_flag(timeron)

!---------------------------------------------------------------------
!---------------------------------------------------------------------

  implicit none
  logical timeron

  integer nc, ios
  character(len=20) val

  timeron = .false.

! ... Check environment variable "NPB_TIMER_FLAG"
  call get_environment_variable('NPB_TIMER_FLAG', val, nc, ios)
  if (ios .eq. 0) then
    if (nc .le. 0) then
      timeron = .true.
    else if (val(1:1) .ge. '1' .and. val(1:1) .le. '9') then
      timeron = .true.
    else if (val .eq. 'on' .or. val .eq. 'ON' .or.  &
    &            val .eq. 'yes' .or. val .eq. 'YES' .or.  &
    &            val .eq. 'true' .or. val .eq. 'TRUE') then
      timeron = .true.
    end if

  else

! ... Check if the "timer.flag" file exists
    open (unit=2, file='timer.flag', status='old', iostat=ios)
    if (ios .eq. 0) then
      close (2)
      timeron = .true.
    end if

  end if

  return
end

